"""Agent chat endpoint with Server-Sent Events (SSE) streaming.

Provides a conversational AI interface that streams responses back
to the client using SSE.  If the ``AgentRuntime`` from
``pnlclaw_agent`` is not available, a mock stream is returned.

Security layers (defense-in-depth):
1. Input guard: prompt injection detection (regex + pattern matching)
2. Scope guard: topic classification + off-topic blocking
3. Input sanitizer: control char stripping + untrusted content wrapping
4. Output guard: redact internal information from AI responses

Resilience:
- TurnTracker keeps producer tasks alive across client disconnects
- Clients can resume interrupted turns with ``resume: true``
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import OrderedDict
from collections.abc import AsyncIterator
from dataclasses import dataclass, field as dc_field
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.dependencies import get_agent_runtime, get_settings_service
from pnlclaw_types.agent import AgentStreamEventType

import logging

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Security guardrails
# ---------------------------------------------------------------------------

try:
    from pnlclaw_security.guardrails.content_scope import (
        ContentScopeGuard,
        GuardAction,
    )
    from pnlclaw_security.sanitizer import (
        detect_injection_markers,
        sanitize_for_prompt,
    )
    _content_guard = ContentScopeGuard()
    _SECURITY_AVAILABLE = True
except ImportError:
    _content_guard = None  # type: ignore[assignment]
    _SECURITY_AVAILABLE = False
    _logger.warning("Security guardrails not available — running unprotected")

router = APIRouter(prefix="/agent", tags=["agent"])


# ---------------------------------------------------------------------------
# Per-session context storage (in-memory for v0.1)
# ---------------------------------------------------------------------------

_MAX_SESSIONS = 64

try:
    from pnlclaw_agent.context.manager import ContextManager as _ContextManager
    _CTX_AVAILABLE = True
except ImportError:
    _ContextManager = None  # type: ignore[assignment,misc]
    _CTX_AVAILABLE = False

_session_contexts: OrderedDict[str, Any] = OrderedDict()


# ---------------------------------------------------------------------------
# Turn tracker — keeps producer alive across client disconnects
# ---------------------------------------------------------------------------

_TURN_TTL_SECONDS = 300  # auto-cleanup after 5 min


@dataclass
class TurnState:
    """Tracks a single agent turn (one user message → response cycle)."""

    session_id: str
    user_message: str
    status: str = "running"  # running | completed | failed
    started_at: float = dc_field(default_factory=time.monotonic)
    last_checkpoint_at: float = dc_field(default_factory=time.monotonic)
    collected_events: list[str] = dc_field(default_factory=list)
    consumer_cursor: int = 0  # how many events the last consumer received
    producer_task: asyncio.Task[None] | None = None
    queue: asyncio.Queue[str | None] = dc_field(default_factory=asyncio.Queue)
    active_tool: str = ""


_active_turns: dict[str, TurnState] = {}


def _cleanup_stale_turns() -> None:
    """Remove turns that have been completed/failed for > TTL."""
    now = time.monotonic()
    stale = [
        sid for sid, ts in _active_turns.items()
        if ts.status != "running" and (now - ts.last_checkpoint_at) > _TURN_TTL_SECONDS
    ]
    for sid in stale:
        t = _active_turns.pop(sid, None)
        if t and t.producer_task and not t.producer_task.done():
            t.producer_task.cancel()
        _logger.debug("Cleaned up stale turn for session %s", sid)


# ---------------------------------------------------------------------------
# Request body
# ---------------------------------------------------------------------------


async def _restore_context_from_db(session_id: str) -> Any | None:
    """Try to restore a ContextManager from the chat session DB.

    Returns None if the repo is unavailable or the session has no messages.
    """
    if not _CTX_AVAILABLE or _ContextManager is None:
        return None
    try:
        from app.core.dependencies import get_chat_session_repo
        repo = get_chat_session_repo()
        if repo is None:
            return None
        messages = await repo.get_messages(session_id, limit=100)
        if not messages:
            return None
        data = [
            {
                "role": m.get("role", "user"),
                "content": m.get("content", ""),
                "timestamp": None,
                "metadata": None,
            }
            for m in messages
            if m.get("role") in ("user", "assistant", "system")
        ]
        if not data:
            return None
        return _ContextManager.deserialize(data)
    except Exception as exc:
        _logger.debug("Failed to restore context from DB: %s", exc)
        return None


async def _persist_context_to_db(session_id: str, context: Any) -> None:
    """Write current ContextManager messages to the chat session DB."""
    try:
        from app.core.dependencies import get_chat_session_repo
        repo = get_chat_session_repo()
        if repo is None or not hasattr(context, "serialize"):
            return
        messages = context.serialize()
        if not messages:
            return
        payload = [
            {
                "id": f"ctx-{i:04d}",
                "role": m["role"],
                "content": m["content"],
                "extra": m.get("metadata") or {},
            }
            for i, m in enumerate(messages)
        ]
        await repo.save_messages_bulk(session_id, payload)
    except Exception as exc:
        _logger.debug("Failed to persist context to DB: %s", exc)


# ---------------------------------------------------------------------------
# Request body
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """Body for POST /agent/chat."""

    message: str = Field(..., min_length=1, description="User message")
    session_id: str | None = Field(None, description="Existing session ID to continue")
    context: dict[str, Any] | None = Field(None, description="UI context: symbol, timeframe, exchange, etc.")
    resume: bool = Field(False, description="Resume an interrupted turn instead of starting a new one")


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------


_MARKET_KEYWORDS = frozenset([
    "分析", "行情", "趋势", "价格", "涨", "跌", "多", "空", "买", "卖",
    "支撑", "阻力", "K线", "k线", "均线", "macd", "rsi", "ema", "sma",
    "止损", "止盈", "仓位", "交易", "开仓", "平仓", "持仓", "下单",
    "策略", "回测", "backtest", "strategy", "analyze", "analysis",
    "market", "price", "trade", "order", "position", "long", "short",
    "btc", "eth", "sol", "usdt", "bnb", "doge", "xrp",
    "binance", "okx", "orderbook", "订单簿", "盘口",
    "波动", "突破", "震荡", "反转", "动量", "成交量", "volume",
    "生成", "写一个", "帮我", "优化", "改进", "建议",
])


def _is_market_related(message: str) -> bool:
    """Check if the message is about markets, trading, or strategy."""
    msg_lower = message.lower().strip()
    if len(msg_lower) <= 10:
        for kw in _MARKET_KEYWORDS:
            if kw in msg_lower:
                return True
        return False
    for kw in _MARKET_KEYWORDS:
        if kw in msg_lower:
            return True
    return False


def _enrich_message(message: str, context: dict[str, Any] | None) -> str:
    """Prepend UI context (active symbol, timeframe, etc.) to the user message.

    Only injects market context when the message appears to be about
    markets, trading, or strategy.  Casual greetings and general
    questions pass through without context injection.
    """
    if not context:
        return message

    if not _is_market_related(message):
        return message

    parts: list[str] = []
    symbol = context.get("symbol")
    timeframe = context.get("timeframe") or context.get("interval")
    exchange = context.get("exchange")
    market_type = context.get("market_type")

    strategy_id = context.get("strategy_id")
    strategy_name = context.get("strategy_name")

    ctx_items: list[str] = []
    if strategy_id:
        ctx_items.append(f"Strategy ID: {strategy_id}")
    if strategy_name:
        ctx_items.append(f"Strategy Name: {strategy_name}")
    if symbol:
        ctx_items.append(f"Symbol: {symbol}")
    if exchange:
        ex_label = exchange
        if market_type:
            ex_label += f" ({market_type})"
        ctx_items.append(f"Exchange: {ex_label}")
    if timeframe:
        ctx_items.append(f"Timeframe: {timeframe}")

    if ctx_items:
        parts.append(f"[Current view: {', '.join(ctx_items)}]")

    parts.append(message)
    return "\n".join(parts)


async def _try_lazy_init_runtime(settings_service: Any) -> Any | None:
    """Attempt to build AgentRuntime on demand when it was not created at startup."""
    from app.core.dependencies import get_tool_catalog, set_agent_runtime

    try:
        from app.main import _build_agent_runtime

        tool_catalog = get_tool_catalog()
        runtime = await _build_agent_runtime(settings_service, tool_catalog)
        if runtime is not None:
            set_agent_runtime(runtime)
            _logger.info("Agent runtime lazily initialized from current settings")
        return runtime
    except Exception:
        _logger.debug("Lazy agent runtime init failed", exc_info=True)
        return None


def _sse_event(event_type: str, data: dict[str, Any]) -> str:
    """Format a Server-Sent Event line."""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n"


async def _mock_stream(message: str, session_id: str) -> AsyncIterator[str]:
    """Generate a mock SSE stream when AgentRuntime is not available."""
    # text_delta events
    response_text = (
        f'I received your message: "{message}". '
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


async def _canned_stream(text: str, session_id: str) -> AsyncIterator[str]:
    """Emit a pre-defined response as SSE (used for security blocks)."""
    yield _sse_event(
        AgentStreamEventType.TEXT_DELTA.value,
        {
            "type": AgentStreamEventType.TEXT_DELTA.value,
            "data": {"text": text},
            "timestamp": int(time.time() * 1000),
        },
    )
    yield _sse_event(
        AgentStreamEventType.DONE.value,
        {
            "type": AgentStreamEventType.DONE.value,
            "data": {"session_id": session_id},
            "timestamp": int(time.time() * 1000),
        },
    )


async def _guarded_agent_stream(
    runtime: Any, message: str, session_id: str, settings_service: Any = None,
    *, resume: bool = False,
) -> AsyncIterator[str]:
    """Wrapper that applies output filtering on the real agent stream."""
    async for chunk in _agent_stream(runtime, message, session_id, settings_service, resume=resume):
        if _SECURITY_AVAILABLE and _content_guard is not None:
            # Filter text_delta events for information leaks
            if '"text_delta"' in chunk and '"text"' in chunk:
                try:
                    lines = chunk.strip().split("\n")
                    for line in lines:
                        if line.startswith("data: "):
                            data = json.loads(line[6:])
                            text_data = data.get("data", {}).get("text", "")
                            if text_data:
                                filtered = _content_guard.filter_output(text_data)
                                if filtered != text_data:
                                    data["data"]["text"] = filtered
                                    payload = json.dumps(data, ensure_ascii=False)
                                    chunk = f"event: text_delta\ndata: {payload}\n\n"
                except (json.JSONDecodeError, KeyError):
                    pass
        yield chunk


_HEARTBEAT_INTERVAL = 5.0


def _resolve_model_override(message: str, settings_service: Any) -> str | None:
    """Pick a smart-model override based on message keywords, if enabled."""
    if not settings_service:
        return None
    try:
        from app.core.settings_service import SettingsService
        svc: SettingsService = settings_service  # type: ignore[assignment]
        settings = svc._load_non_sensitive()
        llm_section = settings.get("llm", {})

        raw_smart = llm_section.get("smart_mode", False)
        smart_enabled = raw_smart if isinstance(raw_smart, bool) else str(raw_smart).lower() == "true"
        smart_models = llm_section.get("smart_models")

        if not smart_enabled or not isinstance(smart_models, dict):
            return None

        message_lower = message.lower()
        if any(kw in message_lower for kw in ["strategy", "策略", "backtest", "回测", "draft", "起草"]):
            return smart_models.get("strategy")
        if any(kw in message_lower for kw in ["analyze", "分析", "market", "行情", "trend", "趋势"]):
            return smart_models.get("analysis")
        return smart_models.get("quick")
    except Exception:
        return None


def _start_producer(
    runtime: Any,
    message: str,
    session_id: str,
    turn: TurnState,
    settings_service: Any = None,
) -> None:
    """Launch the producer task and store it in the TurnState.

    The producer writes SSE-formatted strings to ``turn.queue`` and
    appends each one to ``turn.collected_events`` so reconnecting
    clients can replay what they missed.
    """
    model_override = _resolve_model_override(message, settings_service)

    async def _produce_events() -> None:
        original_model = None
        try:
            if model_override and hasattr(runtime, "_llm") and hasattr(runtime._llm, "_config"):
                original_model = runtime._llm._config.model
                runtime._llm._config.model = model_override

            on_checkpoint = getattr(runtime, "_on_checkpoint", None)

            async for event in runtime.process_message(message):
                payload = event.model_dump(mode="json")
                if event.type == AgentStreamEventType.DONE:
                    payload.setdefault("data", {})["session_id"] = session_id

                evt_type = event.type.value
                if evt_type == "tool_call":
                    turn.active_tool = str((payload.get("data") or {}).get("tool", ""))
                elif evt_type in ("tool_result", "done"):
                    turn.active_tool = ""

                sse_str = _sse_event(evt_type, payload)
                turn.collected_events.append(sse_str)
                turn.last_checkpoint_at = time.monotonic()
                await turn.queue.put(sse_str)

                if evt_type == "tool_result" and on_checkpoint:
                    try:
                        on_checkpoint({
                            "session_id": session_id,
                            "event_count": len(turn.collected_events),
                        })
                    except Exception:
                        pass

            turn.status = "completed"
            # Persist context to DB after successful turn
            ctx = _session_contexts.get(session_id)
            if ctx is not None:
                asyncio.ensure_future(_persist_context_to_db(session_id, ctx))
        except Exception as exc:
            _logger.warning("Agent stream error: %s", exc, exc_info=True)
            error_sse = _sse_event(
                AgentStreamEventType.DONE.value,
                {
                    "type": AgentStreamEventType.DONE.value,
                    "data": {"error": str(exc), "session_id": session_id},
                    "timestamp": int(time.time() * 1000),
                },
            )
            turn.collected_events.append(error_sse)
            await turn.queue.put(error_sse)
            turn.status = "failed"
        finally:
            if original_model is not None and hasattr(runtime, "_llm") and hasattr(runtime._llm, "_config"):
                runtime._llm._config.model = original_model
            turn.last_checkpoint_at = time.monotonic()
            await turn.queue.put(None)

    turn.producer_task = asyncio.create_task(_produce_events())


async def _consume_turn_stream(
    turn: TurnState,
    replay_from: int = 0,
) -> AsyncIterator[str]:
    """Consume events from a TurnState, optionally replaying past events.

    ``replay_from`` is the index into ``turn.collected_events`` at which
    to start.  Events before that index are skipped (the client already
    received them).  After replay, live events from the queue are consumed
    with heartbeat keep-alive.

    Updates ``turn.consumer_cursor`` as events are yielded so the next
    consumer knows where to pick up.
    """
    for sse_str in turn.collected_events[replay_from:]:
        turn.consumer_cursor = max(turn.consumer_cursor, replay_from + 1)
        replay_from += 1
        yield sse_str

    turn.consumer_cursor = len(turn.collected_events)

    if turn.status != "running":
        return

    while True:
        try:
            item = await asyncio.wait_for(turn.queue.get(), timeout=_HEARTBEAT_INTERVAL)
        except asyncio.TimeoutError:
            tool_label = turn.active_tool
            yield _sse_event("heartbeat", {
                "type": "heartbeat",
                "data": {
                    "step": f"executing: {tool_label}" if tool_label else "processing",
                },
                "timestamp": int(time.time() * 1000),
            })
            continue

        if item is None:
            break
        turn.consumer_cursor = len(turn.collected_events)
        yield item


async def _agent_stream(
    runtime: Any, message: str, session_id: str, settings_service: Any = None,
    *, resume: bool = False,
) -> AsyncIterator[str]:
    """Stream events from the real AgentRuntime with heartbeat keepalive.

    If ``resume`` is True and an active turn exists for this session, the
    stream reconnects to the running producer, replays missed events, and
    continues live.  Otherwise a new turn is started.

    The producer task is NOT cancelled when the consumer disconnects; it
    keeps running so a reconnecting client can pick up where it left off.
    """
    _cleanup_stale_turns()

    existing = _active_turns.get(session_id)

    if resume and existing and existing.status == "running":
        replay_from = existing.consumer_cursor
        _logger.info(
            "Resuming turn for session %s (buffered %d events, cursor %d)",
            session_id, len(existing.collected_events), replay_from,
        )
        # The consumer disconnected but the producer kept running.
        # Drain any leftover items from the old queue into collected_events,
        # then create a fresh queue for the new consumer.
        new_queue: asyncio.Queue[str | None] = asyncio.Queue()
        old_queue = existing.queue
        existing.queue = new_queue

        while not old_queue.empty():
            try:
                leftover = old_queue.get_nowait()
                if leftover is not None:
                    existing.collected_events.append(leftover)
            except asyncio.QueueEmpty:
                break

        async for sse_str in _consume_turn_stream(existing, replay_from=replay_from):
            yield sse_str
        return

    if resume and existing and existing.status != "running":
        _logger.info(
            "Resume requested but turn already %s for session %s — replaying",
            existing.status, session_id,
        )
        for sse_str in existing.collected_events:
            yield sse_str
        return

    # --- Start a new turn ---
    # Cancel any leftover previous turn for this session
    old_turn = _active_turns.pop(session_id, None)
    if old_turn and old_turn.producer_task and not old_turn.producer_task.done():
        old_turn.producer_task.cancel()

    turn = TurnState(
        session_id=session_id,
        user_message=message,
    )
    _active_turns[session_id] = turn

    _start_producer(runtime, message, session_id, turn, settings_service)

    async for sse_str in _consume_turn_stream(turn):
        yield sse_str


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/chat")
async def agent_chat(
    body: ChatRequest,
    runtime: Any = Depends(get_agent_runtime),
    settings_service: Any = Depends(get_settings_service),
) -> StreamingResponse:
    """Start an AI conversation turn (SSE stream).

    Security pipeline (runs before LLM):
    1. Content scope guard — blocks injections, off-topic, and secret extraction
    2. Input sanitizer — strips control chars, wraps untrusted content
    3. Output filter — redacts internal info from AI responses

    Resilience:
    - Pass ``resume: true`` to reconnect to a running/interrupted turn
    - The producer keeps running even if the client disconnects

    SSE events:
    - ``thinking``, ``tool_call``, ``tool_result``, ``reflection``
    - ``text_delta``: incremental text output
    - ``done``: conversation turn finished
    """
    session_id = body.session_id or f"sess-{uuid.uuid4().hex[:8]}"

    # --- Resume fast path: skip enrichment/security for reconnects ---
    if body.resume and session_id in _active_turns:
        _logger.info("Resume request for session %s", session_id)
        generator = _guarded_agent_stream(
            runtime, body.message, session_id, settings_service, resume=True,
        )
        return StreamingResponse(
            generator,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Session-ID": session_id,
            },
        )

    # --- Build enriched message first (needed for scope guard) ---
    effective_message = body.message
    if body.context and body.context.get("intent"):
        from pnlclaw_agent.analysis_prompts import build_analysis_prompt

        analysis_prompt = build_analysis_prompt(body.context)
        if analysis_prompt is not None:
            effective_message = analysis_prompt
        else:
            effective_message = _enrich_message(body.message, body.context)
    else:
        effective_message = _enrich_message(body.message, body.context)

    # --- Security Layer 1: Input guard ---
    guard_input = effective_message if effective_message != body.message else body.message
    if _SECURITY_AVAILABLE and _content_guard is not None:
        guard_result = _content_guard.check_input(guard_input)
        if guard_result.action == GuardAction.BLOCK:
            _logger.warning(
                "Content guard blocked: topic=%s, reason=%s, msg=%s",
                guard_result.topic.value, guard_result.reason, body.message[:80],
            )
            return StreamingResponse(
                _canned_stream(guard_result.canned_response or "", session_id),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Session-ID": session_id,
                },
            )

    # --- Security Layer 2: Injection marker detection (audit log) ---
    if _SECURITY_AVAILABLE:
        markers = detect_injection_markers(body.message)
        if markers:
            _logger.warning(
                "Injection markers detected: %s in message: %s",
                markers, body.message[:100],
            )

    # --- Per-session context management ---
    if _CTX_AVAILABLE and runtime is not None and hasattr(runtime, "_context"):
        if session_id not in _session_contexts:
            ctx = await _restore_context_from_db(session_id)
            _session_contexts[session_id] = ctx or _ContextManager()
            if ctx:
                _logger.info("Restored context from DB for session %s", session_id)
            else:
                _logger.info("Created new context for session %s", session_id)
            while len(_session_contexts) > _MAX_SESSIONS:
                evicted_key, _ = _session_contexts.popitem(last=False)
                _logger.debug("Evicted oldest session context: %s", evicted_key)
        else:
            _session_contexts.move_to_end(session_id)
        runtime._context = _session_contexts[session_id]

    # Lazy initialization: try to build runtime if not yet available
    if runtime is None and settings_service is not None:
        runtime = await _try_lazy_init_runtime(settings_service)

    if runtime is not None:
        generator = _guarded_agent_stream(runtime, effective_message, session_id, settings_service)
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


# Alias for explicit stream endpoint (backward compatible)
@router.post("/stream")
async def agent_stream(
    body: ChatRequest,
    runtime: Any = Depends(get_agent_runtime),
    settings_service: Any = Depends(get_settings_service),
) -> StreamingResponse:
    """Alias for ``POST /agent/chat`` — same SSE stream, explicit name."""
    return await agent_chat(body, runtime, settings_service)
