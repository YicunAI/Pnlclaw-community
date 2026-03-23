"""Agent chat endpoint with Server-Sent Events (SSE) streaming.

Provides a conversational AI interface that streams responses back
to the client using SSE.  If the ``AgentRuntime`` from
``pnlclaw_agent`` is not available, a mock stream is returned.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from pnlclaw_types.agent import AgentStreamEventType
from pnlclaw_types.common import APIResponse, ResponseMeta

from app.core.dependencies import get_agent_runtime

router = APIRouter(prefix="/agent", tags=["agent"])


# ---------------------------------------------------------------------------
# Session storage (in-memory for v0.1)
# ---------------------------------------------------------------------------

_sessions: dict[str, list[dict[str, Any]]] = {}


# ---------------------------------------------------------------------------
# Request body
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """Body for POST /agent/chat."""

    message: str = Field(..., min_length=1, description="User message")
    session_id: str | None = Field(None, description="Existing session ID to continue")


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------


def _sse_event(event_type: str, data: dict[str, Any]) -> str:
    """Format a Server-Sent Event line."""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n"


async def _mock_stream(message: str, session_id: str) -> AsyncIterator[str]:
    """Generate a mock SSE stream when AgentRuntime is not available."""
    # text_delta events
    response_text = (
        f"I received your message: \"{message}\". "
        "The agent runtime is not yet connected. "
        "This is a placeholder response from the API layer."
    )
    # Stream word by word
    words = response_text.split()
    for i, word in enumerate(words):
        delta = word + (" " if i < len(words) - 1 else "")
        yield _sse_event(
            AgentStreamEventType.TEXT_DELTA.value,
            {
                "type": AgentStreamEventType.TEXT_DELTA.value,
                "data": {"text": delta},
                "timestamp": int(time.time() * 1000),
            },
        )

    # done event
    yield _sse_event(
        AgentStreamEventType.DONE.value,
        {
            "type": AgentStreamEventType.DONE.value,
            "data": {"session_id": session_id},
            "timestamp": int(time.time() * 1000),
        },
    )


async def _agent_stream(
    runtime: Any, message: str, session_id: str
) -> AsyncIterator[str]:
    """Stream events from the real AgentRuntime."""
    try:
        async for event in runtime.process_message(message):
            yield _sse_event(
                event.type.value,
                event.model_dump(mode="json"),
            )
    except Exception as exc:
        yield _sse_event(
            AgentStreamEventType.DONE.value,
            {
                "type": AgentStreamEventType.DONE.value,
                "data": {"error": str(exc), "session_id": session_id},
                "timestamp": int(time.time() * 1000),
            },
        )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/chat")
async def agent_chat(
    body: ChatRequest,
    runtime: Any = Depends(get_agent_runtime),
) -> StreamingResponse:
    """Start an AI conversation turn (SSE stream).

    The response is a ``text/event-stream`` with events:
    - ``text_delta``: incremental text output
    - ``tool_call``: agent invoked a tool
    - ``tool_result``: tool execution result
    - ``done``: conversation turn finished
    """
    session_id = body.session_id or f"sess-{uuid.uuid4().hex[:8]}"

    # Track conversation history
    history = _sessions.setdefault(session_id, [])
    history.append({"role": "user", "content": body.message})

    if runtime is not None:
        generator = _agent_stream(runtime, body.message, session_id)
    else:
        generator = _mock_stream(body.message, session_id)

    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Session-ID": session_id,
        },
    )
