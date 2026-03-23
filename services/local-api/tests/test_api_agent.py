"""Tests for agent chat endpoint (S3-L06)."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.dependencies import get_agent_runtime
from app.main import create_app

import app.api.v1.agent as _mod


@pytest.fixture(autouse=True)
def _clear_sessions():
    _mod._sessions.clear()
    yield
    _mod._sessions.clear()


def _app(runtime=None):
    app = create_app()
    app.dependency_overrides[get_agent_runtime] = lambda: runtime
    return app


@pytest.mark.asyncio
async def test_chat_returns_sse():
    app = _app(None)  # mock stream
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/agent/chat",
            json={"message": "Hello"},
        )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert "X-Session-ID" in resp.headers


@pytest.mark.asyncio
async def test_chat_sse_events_parseable():
    app = _app(None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/agent/chat",
            json={"message": "Hi there"},
        )

    # Parse SSE events from response body
    events = []
    for line in resp.text.split("\n"):
        if line.startswith("data: "):
            data = json.loads(line[6:])
            events.append(data)

    assert len(events) > 0
    # Last event should be "done"
    assert events[-1]["type"] == "done"
    # Earlier events should be "text_delta"
    assert events[0]["type"] == "text_delta"


@pytest.mark.asyncio
async def test_chat_with_session_id():
    app = _app(None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # First message
        resp1 = await c.post(
            "/api/v1/agent/chat",
            json={"message": "First"},
        )
        session_id = resp1.headers["x-session-id"]

        # Second message with same session
        resp2 = await c.post(
            "/api/v1/agent/chat",
            json={"message": "Second", "session_id": session_id},
        )
    assert resp2.headers["x-session-id"] == session_id


@pytest.mark.asyncio
async def test_chat_session_history():
    app = _app(None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp1 = await c.post(
            "/api/v1/agent/chat",
            json={"message": "Hello"},
        )
        sid = resp1.headers["x-session-id"]
        await c.post(
            "/api/v1/agent/chat",
            json={"message": "World", "session_id": sid},
        )

    # Internal session should have 2 messages
    assert len(_mod._sessions[sid]) == 2
