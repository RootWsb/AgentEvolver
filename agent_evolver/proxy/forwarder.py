"""Forward requests to upstream LLM via httpx.AsyncClient."""

from typing import Any

import httpx

from agent_evolver.config import get_config

_config = get_config()

_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=_config.evolver_upstream_base_url,
            timeout=httpx.Timeout(120.0, connect=10.0),
            headers={
                "Authorization": f"Bearer {_config.evolver_upstream_api_key}",
                "Content-Type": "application/json",
            },
            http2=True,
        )
    return _client


async def forward_chat_completion(payload: dict[str, Any]) -> dict[str, Any]:
    """Forward a chat completion request to upstream LLM.

    Returns the full JSON response.
    Raises on upstream error (non-2xx or invalid JSON).
    """
    client = get_http_client()

    # Clone payload so we don't mutate caller's dict
    body = dict(payload)

    # Strip any non-standard keys that might confuse upstream
    body.pop("session_id", None)
    body.pop("session_done", None)
    body.pop("turn_type", None)

    # Force non-streaming for MVP (simplifies recording)
    body["stream"] = False

    resp = await client.post("/chat/completions", json=body)

    # Build a rich error message before raising
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        # Try to include upstream error body in the exception message
        try:
            err_body = resp.json()
            err_detail = err_body.get("error", {}).get("message", str(err_body))
        except Exception:
            err_detail = resp.text[:500]  # truncated raw body
        raise httpx.HTTPStatusError(
            f"Upstream error {resp.status_code}: {err_detail}",
            request=exc.request,
            response=exc.response,
        ) from exc

    return resp.json()


async def close_http_client() -> None:
    global _client
    if _client:
        await _client.aclose()
        _client = None
