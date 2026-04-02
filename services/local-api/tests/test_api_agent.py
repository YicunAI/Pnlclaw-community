"""Tests for agent chat endpoint (S3-L06)."""

from __future__ import annotations

import json

import app.api.v1.agent as _mod
import pytest
from app.core.dependencies import get_agent_runtime, get_settings_service
from app.main import create_app
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def _clear_sessions():
    _mod._session_contexts.clear()
    _mod._active_turns.clear()
    yield
    _mod._session_contexts.clear()
    _mod._active_turns.clear()


def _app(runtime=None):
    app = create_app()
    app.dependency_overrides[get_agent_runtime] = lambda: runtime
    if runtime is None:
        app.dependency_overrides[get_settings_service] = lambda: None
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
async def test_chat_with_backtest_explain_context_returns_sse():
    app = _app(None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/agent/chat",
            json={
                "message": "Explain this backtest",
                "context": {
                    "intent": "backtest_explain",
                    "backtest_id": "bt-123",
                    "strategy_id": "strat-123",
                    "strategy_name": "MACD Momentum",
                    "symbol": "BTC/USDT",
                    "timeframe": "1h",
                    "metrics": {
                        "total_return": 0.12,
                        "sharpe_ratio": 1.8,
                        "max_drawdown": -0.08,
                        "win_rate": 0.55,
                        "profit_factor": 1.6,
                        "total_trades": 42,
                    },
                },
            },
        )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    events = [json.loads(line[6:]) for line in resp.text.split("\n") if line.startswith("data: ")]
    assert events[-1]["type"] == "done"

    app = _app(None)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp1 = await c.post(
            "/api/v1/agent/chat",
            json={"message": "Hello"},
        )
        sid = resp1.headers["x-session-id"]
        resp2 = await c.post(
            "/api/v1/agent/chat",
            json={"message": "World", "session_id": sid},
        )

    assert resp2.headers["x-session-id"] == sid
