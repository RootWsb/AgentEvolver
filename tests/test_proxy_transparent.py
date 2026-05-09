"""Test that the proxy transparently forwards requests without modifying responses."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from agent_evolver.proxy.server import app
    return TestClient(app)


def test_list_models_endpoint(client):
    """/v1/models returns the configured upstream model (no upstream call)."""
    resp = client.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["object"] == "list"
    assert len(data["data"]) == 1
    assert data["data"][0]["owned_by"] == "agent-evolver"


def test_chat_completion_forwards_payload(client, monkeypatch):
    """Proxy accepts a standard OpenAI chat completion payload and forwards it."""
    # Mock the forwarder so we don't hit a real upstream
    async def _mock_forward(body):
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1234567890,
            "model": body.get("model", "gpt-4o-mini"),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "Hello back"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

    monkeypatch.setattr(
        "agent_evolver.proxy.server.forward_chat_completion", _mock_forward
    )

    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "Hello"}],
        "session_id": "test-session-001",
        "session_done": False,
    }
    resp = client.post("/v1/chat/completions", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["choices"][0]["message"]["content"] == "Hello back"
    assert data["usage"]["total_tokens"] == 15


def test_proxy_strips_internal_fields(client, monkeypatch):
    """Internal fields (session_id, session_done, turn_type) are removed before forwarding."""
    captured_body = {}

    async def _mock_capture(body):
        captured_body.update(body)
        return {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1234567890,
            "model": body.get("model", "gpt-4o-mini"),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    monkeypatch.setattr(
        "agent_evolver.proxy.server.forward_chat_completion", _mock_capture
    )

    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "test"}],
        "session_id": "test-session-002",
        "session_done": True,
        "turn_type": "task_post",
        "stream": True,
    }
    resp = client.post("/v1/chat/completions", json=payload)
    assert resp.status_code == 200

    # Internal fields must NOT reach the upstream forwarder
    assert "session_id" not in captured_body
    assert "session_done" not in captured_body
    assert "turn_type" not in captured_body
    # stream should be forced to False by forwarder
    assert captured_body.get("stream") is False
