"""Tests for Agent SSE + WS streaming protocol (Sprint 1.3).

Validates that the SSE stream correctly transmits the full ReAct event
sequence (thinking → tool_call → tool_result → reflection → text_delta → done)
and that the WS endpoint maps events consistently.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

import pytest
from app.core.dependencies import get_agent_runtime, get_settings_service
from app.main import create_app
from httpx import ASGITransport, AsyncClient
from pnlclaw_types.agent import AgentStreamEvent, AgentStreamEventType


# ---------------------------------------------------------------------------
# Mock runtime that produces a full ReAct event sequence
# ---------------------------------------------------------------------------

class _ReActMockRuntime:
    """Produces the canonical event sequence for testing."""

    async def process_message(self, message: str) -> AsyncIterator[AgentStreamEvent]:
        ts = int(time.time() * 1000)

        yield AgentStreamEvent(
            type=AgentStreamEventType.THINKING,
            data={"content": "Let me check the market price...", "round": 1},
            timestamp=ts,
        )
        yield AgentStreamEvent(
            type=AgentStreamEventType.TOOL_CALL,
            data={"tool": "market_ticker", "arguments": {"symbol": "BTC/USDT"}},
            timestamp=ts + 1,
        )
        yield AgentStreamEvent(
            type=AgentStreamEventType.TOOL_RESULT,
            data={"tool": "market_ticker", "output": '{"price": 67234.5}'},
            timestamp=ts + 2,
        )
        yield AgentStreamEvent(
            type=AgentStreamEventType.REFLECTION,
            data={"content": "Got price data, sufficient to answer.", "round": 1},
            timestamp=ts + 3,
        )
        yield AgentStreamEvent(
            type=AgentStreamEventType.TEXT_DELTA,
            data={"text": "BTC is currently $67,234.50."},
            timestamp=ts + 4,
        )
        yield AgentStreamEvent(
            type=AgentStreamEventType.DONE,
            data={},
            timestamp=ts + 5,
        )


def _make_app():
    app = create_app()
    app.dependency_overrides[get_agent_runtime] = lambda: _ReActMockRuntime()
    app.dependency_overrides[get_settings_service] = lambda: None
    return app


def _parse_sse_events(body: str) -> list[dict[str, Any]]:
    """Parse raw SSE text into a list of {event_type, data} dicts."""
    events: list[dict[str, Any]] = []
    current_event: str | None = None
    current_data: str | None = None

    for line in body.split("\n"):
        if line.startswith("event: "):
            current_event = line[7:].strip()
        elif line.startswith("data: "):
            current_data = line[6:].strip()
        elif line == "" and current_event is not None and current_data is not None:
            try:
                data = json.loads(current_data)
            except json.JSONDecodeError:
                data = current_data
            events.append({"event_type": current_event, "data": data})
            current_event = None
            current_data = None

    return events


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sse_contains_thinking_and_reflection():
    """SSE stream must include thinking and reflection events."""
    app = _make_app()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/agent/chat",
            json={"message": "BTC price?"},
        )
        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        types = [e["event_type"] for e in events]
        assert "thinking" in types
        assert "reflection" in types


@pytest.mark.asyncio
async def test_sse_event_order_is_correct():
    """SSE events must follow: thinking before tool_call, reflection after tool_result."""
    app = _make_app()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/agent/chat",
            json={"message": "BTC price?"},
        )
        events = _parse_sse_events(resp.text)
        types = [e["event_type"] for e in events]

        thinking_idx = types.index("thinking")
        tool_call_idx = types.index("tool_call")
        tool_result_idx = types.index("tool_result")
        reflection_idx = types.index("reflection")
        text_idx = types.index("text_delta")

        assert thinking_idx < tool_call_idx
        assert tool_result_idx < reflection_idx
        assert reflection_idx < text_idx


@pytest.mark.asyncio
async def test_sse_backward_compat_done_always_emitted():
    """The done event must always be the last event (backward compatibility)."""
    app = _make_app()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/agent/chat",
            json={"message": "test"},
        )
        events = _parse_sse_events(resp.text)
        assert len(events) > 0
        assert events[-1]["event_type"] == "done"


@pytest.mark.asyncio
async def test_sse_events_contain_valid_json():
    """All SSE data payloads must be valid JSON with type and timestamp."""
    app = _make_app()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/agent/chat",
            json={"message": "test"},
        )
        events = _parse_sse_events(resp.text)
        for ev in events:
            assert isinstance(ev["data"], dict), f"Event data is not dict: {ev}"
            assert "type" in ev["data"], f"Missing type in event data: {ev}"
            assert "timestamp" in ev["data"], f"Missing timestamp in event data: {ev}"


@pytest.mark.asyncio
async def test_stream_alias_returns_same_result():
    """POST /agent/stream must return the same SSE stream as /agent/chat."""
    app = _make_app()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp_chat = await c.post("/api/v1/agent/chat", json={"message": "test"})
        resp_stream = await c.post("/api/v1/agent/stream", json={"message": "test"})
        assert resp_chat.status_code == 200
        assert resp_stream.status_code == 200
        chat_types = [e["event_type"] for e in _parse_sse_events(resp_chat.text)]
        stream_types = [e["event_type"] for e in _parse_sse_events(resp_stream.text)]
        assert chat_types == stream_types


@pytest.mark.asyncio
async def test_sse_thinking_event_has_content_and_round():
    """thinking event data must include content and round fields."""
    app = _make_app()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/api/v1/agent/chat", json={"message": "test"})
        events = _parse_sse_events(resp.text)
        thinking_events = [e for e in events if e["event_type"] == "thinking"]
        assert len(thinking_events) >= 1
        data = thinking_events[0]["data"]["data"]
        assert "content" in data
        assert "round" in data
