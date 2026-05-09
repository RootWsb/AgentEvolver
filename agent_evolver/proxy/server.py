"""FastAPI proxy server — transparently intercepts OpenAI-compatible chat completions."""

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

from agent_evolver.config import get_config
from agent_evolver.proxy.forwarder import forward_chat_completion, close_http_client
from agent_evolver.proxy.recorder import get_recorder
from agent_evolver.storage.db import init_storage_db, get_storage_session
from agent_evolver.engine.triggers import schedule_post_execution

_config = get_config()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB. Shutdown: close HTTP client."""
    init_storage_db()
    yield
    await close_http_client()


app = FastAPI(title="Agent Evolver Proxy", lifespan=lifespan)


def _extract_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return payload.get("messages", [])


def _extract_tool_calls(response: dict[str, Any]) -> list[dict[str, Any]]:
    choices = response.get("choices", [])
    if not choices:
        return []
    msg = choices[0].get("message", {})
    return msg.get("tool_calls", [])


def _extract_content(response: dict[str, Any]) -> str | None:
    choices = response.get("choices", [])
    if not choices:
        return None
    msg = choices[0].get("message", {})
    return msg.get("content")


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.get("/v1/models")
async def list_models():
    """Return the single upstream model."""
    return {
        "object": "list",
        "data": [
            {
                "id": _config.evolver_upstream_model,
                "object": "model",
                "created": 0,
                "owned_by": "agent-evolver",
            }
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """Proxy chat completion: forward to upstream, record session asynchronously."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON body"},
        )

    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content={"error": "Request body must be a JSON object"},
        )

    # Extract session metadata from headers (or body for non-standard agents)
    session_id = request.headers.get("x-session-id") or body.pop("session_id", None)

    # Parse session_done: header string "false" must NOT be treated as True
    header_done = request.headers.get("x-session-done")
    if header_done is not None:
        session_done = header_done.lower() in ("1", "true", "yes")
    else:
        session_done = bool(body.pop("session_done", False))

    # Generate session ID if not provided
    if not session_id:
        session_id = str(uuid.uuid4())

    # Optional metadata for richer session recording
    agent_id = request.headers.get("x-agent-id")
    user_id = request.headers.get("x-user-id")

    recorder = get_recorder()

    # Ensure session exists before recording
    await recorder.start_session(
        session_id=session_id, agent_id=agent_id, user_id=user_id
    )

    # Record user/assistant messages from the request
    messages = _extract_messages(body)
    for msg in messages:
        await recorder.record_message(
            session_id=session_id,
            role=msg.get("role", "unknown"),
            content=msg.get("content"),
        )

    upstream_response: dict[str, Any] | None = None
    try:
        # Forward to upstream LLM (blocking call, but async)
        upstream_response = await forward_chat_completion(body)
    except Exception as e:
        # Record failure and return error to agent
        await recorder.close_session(session_id, status="failed")
        return JSONResponse(
            status_code=502,
            content={"error": "Upstream LLM failed", "detail": str(e)},
        )

    try:
        # Record assistant response
        assistant_content = _extract_content(upstream_response)
        if assistant_content:
            await recorder.record_message(
                session_id=session_id,
                role="assistant",
                content=assistant_content,
            )

        # Record tool calls if any
        for tc in _extract_tool_calls(upstream_response):
            fn = tc.get("function", {})
            await recorder.record_tool_call(
                session_id=session_id,
                tool_name=fn.get("name", "unknown"),
                args=_safe_json_parse(fn.get("arguments")),
                result=None,
                status="invoked",
            )
    finally:
        # Always close session when session_done is set, even if recording fails
        if session_done:
            try:
                total_tokens = upstream_response.get("usage", {}).get("total_tokens")
                await recorder.close_session(
                    session_id=session_id,
                    total_tokens=total_tokens,
                    status="completed",
                )
            except Exception:
                logging.getLogger("agent_evolver.proxy").exception(
                    "Failed to close session %s", session_id
                )

    # Trigger post-execution evolution analysis (fire-and-forget)
    if session_done:
        try:
            db = next(get_storage_session())
            schedule_post_execution(
                db=db,
                session_id=session_id,
                task_completed=True,
            )
        except Exception:
            logging.getLogger("agent_evolver.proxy").exception(
                "Failed to schedule evolution for session %s", session_id
            )

    # Return upstream response verbatim
    return JSONResponse(content=upstream_response)


def _safe_json_parse(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def main() -> None:
    """Entry point for `evolver-proxy` CLI command."""
    uvicorn.run(
        "agent_evolver.proxy.server:app",
        host=_config.evolver_proxy_host,
        port=_config.evolver_proxy_port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
