"""WebSocket gateway for real-time market data and paper trading updates.

Two WebSocket endpoints:
- ``/api/v1/ws/markets`` — subscribe to ticker/kline/depth events
- ``/api/v1/ws/paper`` — receive order/position/PnL state changes

Protocol:
- Client sends JSON messages to subscribe/unsubscribe
- Server pushes JSON event frames
- Heartbeat via WebSocket ping/pong (handled by Starlette)
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.dependencies import get_market_service

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["websocket"])

# Polymarket WS bridge — shared connection per backend instance
_poly_ws_client = None
_poly_ws_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Connection manager
# ---------------------------------------------------------------------------


class ConnectionManager:
    """Track active WebSocket connections and their subscriptions."""

    def __init__(self) -> None:
        self._connections: dict[WebSocket, set[str]] = {}

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[ws] = set()

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.pop(ws, None)

    def subscribe(self, ws: WebSocket, channel: str) -> None:
        if ws in self._connections:
            self._connections[ws].add(channel)

    def unsubscribe(self, ws: WebSocket, channel: str) -> None:
        if ws in self._connections:
            self._connections[ws].discard(channel)

    def get_subscriptions(self, ws: WebSocket) -> set[str]:
        return self._connections.get(ws, set())

    async def broadcast(self, channel: str, data: dict[str, Any]) -> None:
        """Send data to all connections subscribed to *channel*."""
        dead: list[WebSocket] = []
        for ws, channels in list(self._connections.items()):
            if channel in channels:
                try:
                    await ws.send_json(data)
                except Exception:
                    dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    @property
    def active_count(self) -> int:
        return len(self._connections)


# Singleton managers
_market_manager = ConnectionManager()
_paper_manager = ConnectionManager()
_trading_manager = ConnectionManager()
_polymarket_manager = ConnectionManager()
_agent_manager = ConnectionManager()


# ---------------------------------------------------------------------------
# /api/v1/ws/markets
# ---------------------------------------------------------------------------


@router.websocket("/api/v1/ws/markets")
async def ws_markets(ws: WebSocket) -> None:
    """Real-time market data WebSocket.

    Client messages (JSON):
        ``{"action": "subscribe", "symbols": ["BTC/USDT"]}``
        ``{"action": "unsubscribe", "symbols": ["BTC/USDT"]}``

    Server pushes:
        ``{"type": "ticker", "symbol": "BTC/USDT", "data": {...}}``
        ``{"type": "kline", "symbol": "BTC/USDT", "data": {...}}``
        ``{"type": "depth", "symbol": "BTC/USDT", "data": {...}}``
    """
    await _market_manager.connect(ws)
    logger.info("ws_market_connected", connections=_market_manager.active_count)
    try:
        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=60.0)
            except TimeoutError:
                # Send ping to keep connection alive
                try:
                    await ws.send_json({"type": "ping", "timestamp": int(time.time() * 1000)})
                except Exception:
                    break
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            action = msg.get("action")
            symbols = msg.get("symbols", [])

            if action == "subscribe":
                ex = msg.get("exchange", "binance")
                mt = msg.get("market_type", "spot")
                for sym in symbols:
                    _market_manager.subscribe(ws, f"market:{ex}:{mt}:{sym}")
                svc = get_market_service()
                if svc is not None:
                    for sym in symbols:
                        try:
                            await svc.add_symbol(sym, exchange=ex, market_type=mt)
                        except Exception:
                            logger.warning("ws_add_symbol_failed", symbol=sym, exc_info=True)
                await ws.send_json(
                    {
                        "type": "subscribed",
                        "symbols": symbols,
                        "exchange": ex,
                        "market_type": mt,
                        "timestamp": int(time.time() * 1000),
                    }
                )
            elif action == "unsubscribe":
                ex = msg.get("exchange", "binance")
                mt = msg.get("market_type", "spot")
                for sym in symbols:
                    _market_manager.unsubscribe(ws, f"market:{ex}:{mt}:{sym}")
                await ws.send_json(
                    {
                        "type": "unsubscribed",
                        "symbols": symbols,
                        "timestamp": int(time.time() * 1000),
                    }
                )
            else:
                await ws.send_json({"type": "error", "message": f"Unknown action: {action}"})

    except WebSocketDisconnect:
        pass
    finally:
        _market_manager.disconnect(ws)
        logger.info("ws_market_disconnected", connections=_market_manager.active_count)


# ---------------------------------------------------------------------------
# /api/v1/ws/paper
# ---------------------------------------------------------------------------


async def _resolve_ws_user(ws: WebSocket) -> str | None:
    """Extract user_id from the first query param ``token`` on a WS connection.

    Returns the user_id string if auth is enabled and the token is valid,
    ``"local"`` when auth is disabled (Community mode), or ``None`` on failure.
    """
    from app.core.dependencies import get_jwt_manager

    jwt_mgr = get_jwt_manager()
    if jwt_mgr is None:
        return "local"

    token = ws.query_params.get("token", "")
    if not token:
        return None
    try:
        payload = jwt_mgr.decode_access_token(token)
        return payload.get("sub")
    except Exception:
        return None


async def _verify_account_ownership(user_id: str, account_id: str) -> bool:
    """Check if the given user owns the paper account (or auth is disabled)."""
    if user_id == "local":
        return True
    from app.core.dependencies import get_db_manager
    db = get_db_manager()
    if db is None:
        return True
    try:
        from pnlclaw_storage.repositories.paper_accounts import PaperAccountRepository
        repo = PaperAccountRepository(db)
        acct = await repo.get_account(account_id)
        if acct is None:
            return False
        acct_user = acct.get("user_id", "local")
        return acct_user == user_id or acct_user == "local"
    except Exception:
        return True


@router.websocket("/api/v1/ws/paper")
async def ws_paper(ws: WebSocket) -> None:
    """Paper Trading state WebSocket.

    Client messages (JSON):
        ``{"action": "subscribe", "account_id": "pa-xxx"}``
        ``{"action": "unsubscribe", "account_id": "pa-xxx"}``

    Server pushes:
        ``{"type": "order_update", "account_id": "pa-xxx", "data": {...}}``
        ``{"type": "position_update", "account_id": "pa-xxx", "data": {...}}``
        ``{"type": "pnl_update", "account_id": "pa-xxx", "data": {...}}``
    """
    await _paper_manager.connect(ws)
    ws_user_id = await _resolve_ws_user(ws)
    logger.info("ws_paper_connected", connections=_paper_manager.active_count, user=ws_user_id)
    try:
        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=60.0)
            except TimeoutError:
                try:
                    await ws.send_json({"type": "ping", "timestamp": int(time.time() * 1000)})
                except Exception:
                    break
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            action = msg.get("action")
            account_id = msg.get("account_id", "")

            if action == "subscribe" and account_id:
                if ws_user_id is None:
                    await ws.send_json({
                        "type": "error",
                        "message": "Authentication required: provide a valid token query parameter",
                        "timestamp": int(time.time() * 1000),
                    })
                    continue
                if ws_user_id != "local" and not await _verify_account_ownership(ws_user_id, account_id):
                    await ws.send_json({
                        "type": "error",
                        "message": "Access denied: account does not belong to current user",
                        "timestamp": int(time.time() * 1000),
                    })
                    continue
                _paper_manager.subscribe(ws, f"paper:{account_id}")
                await ws.send_json(
                    {
                        "type": "subscribed",
                        "account_id": account_id,
                        "timestamp": int(time.time() * 1000),
                    }
                )
            elif action == "unsubscribe" and account_id:
                _paper_manager.unsubscribe(ws, f"paper:{account_id}")
                await ws.send_json(
                    {
                        "type": "unsubscribed",
                        "account_id": account_id,
                        "timestamp": int(time.time() * 1000),
                    }
                )
            else:
                await ws.send_json({"type": "error", "message": f"Unknown action: {action}"})

    except WebSocketDisconnect:
        pass
    finally:
        _paper_manager.disconnect(ws)
        logger.info("ws_paper_disconnected", connections=_paper_manager.active_count)


# ---------------------------------------------------------------------------
# /api/v1/ws/trading
# ---------------------------------------------------------------------------


@router.websocket("/api/v1/ws/trading")
async def ws_trading(ws: WebSocket) -> None:
    """Unified trading WebSocket — receives order, fill, position, balance events.

    Requires authentication in Pro mode via ``?token=`` query parameter.

    Client messages (JSON):
        ``{"action": "subscribe", "channels": ["orders", "positions", "balances"]}``
        ``{"action": "unsubscribe", "channels": ["orders"]}``

    Server pushes:
        ``{"type": "order_update", "data": {...}}``
        ``{"type": "fill", "data": {...}}``
        ``{"type": "position_update", "data": {...}}``
        ``{"type": "balance_update", "data": [...]}``
    """
    await _trading_manager.connect(ws)
    ws_user_id = await _resolve_ws_user(ws)
    logger.info("ws_trading_connected", connections=_trading_manager.active_count, user=ws_user_id)
    try:
        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=60.0)
            except TimeoutError:
                try:
                    await ws.send_json({"type": "ping", "timestamp": int(time.time() * 1000)})
                except Exception:
                    break
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            action = msg.get("action")
            channels = msg.get("channels", [])

            if action == "subscribe":
                if ws_user_id is None:
                    await ws.send_json({
                        "type": "error",
                        "message": "Authentication required",
                        "timestamp": int(time.time() * 1000),
                    })
                    continue
                for ch in channels:
                    _trading_manager.subscribe(ws, f"trading:{ch}")
                await ws.send_json(
                    {
                        "type": "subscribed",
                        "channels": channels,
                        "timestamp": int(time.time() * 1000),
                    }
                )
            elif action == "unsubscribe":
                for ch in channels:
                    _trading_manager.unsubscribe(ws, f"trading:{ch}")
                await ws.send_json(
                    {
                        "type": "unsubscribed",
                        "channels": channels,
                        "timestamp": int(time.time() * 1000),
                    }
                )
            else:
                await ws.send_json({"type": "error", "message": f"Unknown action: {action}"})

    except WebSocketDisconnect:
        pass
    finally:
        _trading_manager.disconnect(ws)
        logger.info("ws_trading_disconnected", connections=_trading_manager.active_count)


# ---------------------------------------------------------------------------
# /api/v1/ws/agent — Agent reasoning event stream
# ---------------------------------------------------------------------------

# Map internal AgentStreamEventType to WS event names
_AGENT_EVENT_MAP: dict[str, str] = {
    "thinking": "thinking",
    "tool_call": "tool_call",
    "tool_result": "tool_result",
    "reflection": "reflection",
    "text_delta": "final_answer",
    "done": "done",
}


@router.websocket("/api/v1/ws/agent")
async def ws_agent(ws: WebSocket) -> None:
    """Agent reasoning WebSocket — bidirectional agent interaction.

    Requires authentication in Pro mode via ``?token=`` query parameter.

    Client messages (JSON):
        ``{"action": "chat", "message": "BTC 价格多少？", "session_id": "..."}``

    Server pushes (event sequence):
        ``{"type": "reasoning_start", ...}``
        ``{"type": "thinking", "data": {"content": "...", "round": 1}}``
        ``{"type": "tool_call", "data": {"tool": "...", "arguments": {...}}}``
        ``{"type": "tool_result", "data": {"tool": "...", "output": "..."}}``
        ``{"type": "reflection", "data": {"content": "...", "round": 1}}``
        ``{"type": "final_answer", "data": {"text": "..."}}``
        ``{"type": "done", "data": {}}``
    """
    await _agent_manager.connect(ws)
    ws_user_id = await _resolve_ws_user(ws)
    if ws_user_id is None:
        await ws.send_json({"type": "error", "message": "Authentication required"})
        _agent_manager.disconnect(ws)
        await ws.close(code=4001, reason="Authentication required")
        return
    _agent_manager.subscribe(ws, "agent:reasoning")
    logger.info("ws_agent_connected", connections=_agent_manager.active_count, user=ws_user_id)
    try:
        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=120.0)
            except TimeoutError:
                try:
                    await ws.send_json({"type": "ping", "timestamp": int(time.time() * 1000)})
                except Exception:
                    break
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            action = msg.get("action")

            if action == "chat":
                user_message = msg.get("message", "").strip()
                if not user_message:
                    await ws.send_json({"type": "error", "message": "Empty message"})
                    continue
                await _handle_agent_chat_ws(ws, user_message, msg.get("session_id"))
            else:
                await ws.send_json({"type": "error", "message": f"Unknown action: {action}"})

    except WebSocketDisconnect:
        pass
    finally:
        _agent_manager.disconnect(ws)
        logger.info("ws_agent_disconnected", connections=_agent_manager.active_count)


async def _handle_agent_chat_ws(ws: WebSocket, message: str, session_id: str | None) -> None:
    """Process a chat message through AgentRuntime and push events over WS."""
    from app.core.dependencies import get_agent_runtime

    runtime = get_agent_runtime()
    ts = int(time.time() * 1000)

    if runtime is None:
        await ws.send_json({
            "type": "final_answer",
            "data": {"text": "Agent runtime is not available."},
            "timestamp": ts,
        })
        await ws.send_json({"type": "done", "data": {}, "timestamp": ts})
        return

    await ws.send_json({
        "type": "reasoning_start",
        "data": {"session_id": session_id or ""},
        "timestamp": ts,
    })

    try:
        async for event in runtime.process_message(message):
            ws_type = _AGENT_EVENT_MAP.get(event.type.value, event.type.value)
            await ws.send_json({
                "type": ws_type,
                "data": event.data,
                "timestamp": event.timestamp,
            })
    except Exception as exc:
        logger.error("ws_agent_error", error=str(exc), exc_info=True)
        await ws.send_json({
            "type": "error",
            "data": {"message": str(exc)},
            "timestamp": int(time.time() * 1000),
        })
        await ws.send_json({"type": "done", "data": {}, "timestamp": int(time.time() * 1000)})


async def broadcast_agent_event(event_type: str, data: dict[str, Any]) -> None:
    """Push an agent reasoning event to all subscribed WS clients."""
    await _agent_manager.broadcast(
        "agent:reasoning",
        {"type": event_type, "data": data, "timestamp": int(time.time() * 1000)},
    )


# ---------------------------------------------------------------------------
# Helper for broadcasting from other modules
# ---------------------------------------------------------------------------


async def broadcast_market_event(symbol: str, event_type: str, data: dict[str, Any]) -> None:
    """Push a market event to all WebSocket subscribers of that symbol."""
    exchange = data.get("exchange", "binance")
    market_type = data.get("market_type", "spot")
    
    # Broadcast to specific symbol channel (e.g. market:binance:spot:BTC/USDT)
    channel = f"market:{exchange}:{market_type}:{symbol}"
    payload = {
        "type": event_type,
        "symbol": symbol,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    await _market_manager.broadcast(channel, payload)
    
    # Also broadcast to global "ALL" channel for tactical/derivative events
    # This enables global whale detectors and liquidation monitors
    if symbol != "ALL" and event_type in (
        "large_trade",
        "large_order",
        "liquidation",
        "liquidation_stats",
        "funding_rate",
    ):
        all_channel = f"market:{exchange}:{market_type}:ALL"
        await _market_manager.broadcast(all_channel, payload)


async def broadcast_paper_event(account_id: str, event_type: str, data: dict[str, Any]) -> None:
    """Push a paper trading event to all WebSocket subscribers of that account."""
    await _paper_manager.broadcast(
        f"paper:{account_id}",
        {
            "type": event_type,
            "account_id": account_id,
            "data": data,
            "timestamp": int(time.time() * 1000),
        },
    )


async def broadcast_trading_event(channel: str, event_type: str, data: dict[str, Any]) -> None:
    """Push a trading event (order/fill/position/balance) to WS subscribers.

    Args:
        channel: One of 'orders', 'positions', 'balances'.
        event_type: Event type string, e.g. 'order_update', 'fill', 'balance_update'.
        data: Serialized event data.
    """
    await _trading_manager.broadcast(
        f"trading:{channel}",
        {"type": event_type, "data": data, "timestamp": int(time.time() * 1000)},
    )


# ---------------------------------------------------------------------------
# /api/v1/ws/polymarket — real-time prediction market data
# ---------------------------------------------------------------------------


async def _broadcast_poly(event_type: str, data: dict[str, Any], *ids: str) -> None:
    """Broadcast a Polymarket event to all unique non-empty channel IDs."""
    ts = int(time.time() * 1000)
    payload = {"type": event_type, "data": data, "timestamp": ts}
    sent: set[str] = set()
    for cid in ids:
        if cid and cid not in sent:
            sent.add(cid)
            await _polymarket_manager.broadcast(f"poly:{cid}", payload)


async def _on_poly_book(data: dict[str, Any]) -> None:
    asset_id = data.get("asset_id", "")
    market = data.get("market", "")
    await _broadcast_poly("book", data, asset_id, market)


async def _on_poly_price_change(data: dict[str, Any]) -> None:
    market = data.get("market", "")

    # Polymarket sends {market, price_changes: [{asset_id, price, best_bid, best_ask}, ...]}
    # Broadcast per-asset price_change so frontend can key by token_id
    changes = data.get("price_changes", data.get("tokens", data.get("changes", [])))
    if changes:
        for entry in changes:
            if not isinstance(entry, dict):
                continue
            aid = entry.get("asset_id", "")
            if aid:
                await _broadcast_poly("price_change", entry, aid, market)
    else:
        # Fallback: single asset_id at top level
        asset_id = data.get("asset_id", "")
        await _broadcast_poly("price_change", data, asset_id, market)


async def _on_poly_last_trade(data: dict[str, Any]) -> None:
    asset_id = data.get("asset_id", "")
    market = data.get("market", "")
    await _broadcast_poly("last_trade", data, asset_id, market)


async def _on_poly_disconnect() -> None:
    """Called when the Polymarket WS disconnects — invalidate cached client."""
    global _poly_ws_client
    logger.warning("polymarket_ws_disconnected, will reconnect automatically")
    _poly_ws_client = None


async def _ensure_poly_ws():
    """Lazy-init a shared PolymarketWSClient that bridges events to frontends.

    The client has built-in auto-reconnect and PING keepalive per Polymarket docs.
    If the previous client is disconnected, a fresh one is created.
    """
    global _poly_ws_client
    async with _poly_ws_lock:
        if _poly_ws_client is not None and _poly_ws_client.is_connected:
            return _poly_ws_client

        # Discard stale reference
        if _poly_ws_client is not None:
            try:
                await _poly_ws_client.close()
            except Exception:
                logger.debug(
                    "polymarket_stale_ws_client_close_failed",
                    exc_info=True,
                )
            _poly_ws_client = None

        from pnlclaw_exchange.exchanges.polymarket.ws_client import PolymarketWSClient
        from pnlclaw_exchange.exchanges.polymarket.client import detect_local_proxy

        proxy = detect_local_proxy()
        if proxy:
            logger.info("polymarket_ws_using_proxy", proxy=proxy)

        client = PolymarketWSClient(
            on_book=_on_poly_book,
            on_price_change=_on_poly_price_change,
            on_last_trade=_on_poly_last_trade,
            on_disconnect=_on_poly_disconnect,
            auto_reconnect=True,
            stall_timeout_s=90.0,
            proxy=proxy,
        )
        try:
            await client.connect()
            _poly_ws_client = client
            logger.info("polymarket_ws_connected", proxy=proxy or "direct")
        except Exception:
            logger.error("polymarket_ws_connect_failed", exc_info=True)
            try:
                await client.close()
            except Exception:
                logger.debug(
                    "polymarket_ws_client_close_after_connect_failed",
                    exc_info=True,
                )
        return _poly_ws_client


# ---------------------------------------------------------------------------
# REST polling fallback when WS to Polymarket is unavailable
# ---------------------------------------------------------------------------

_poll_subscribed_tokens: set[str] = set()
_poll_task: asyncio.Task[None] | None = None
_POLL_INTERVAL_S = 2.0  # poll every 2 seconds
_poll_index = 0

async def _poll_orderbooks() -> None:
    """Background task: poll REST orderbooks for subscribed tokens and broadcast."""
    from pnlclaw_exchange.exchanges.polymarket.client import PolymarketClient

    global _poll_index
    client = PolymarketClient()
    logger.info("polymarket_rest_poll_started", interval=_POLL_INTERVAL_S)
    try:
        while True:
            await asyncio.sleep(_POLL_INTERVAL_S)

            # If WS reconnected, stop polling
            if _poly_ws_client is not None and _poly_ws_client.is_connected:
                logger.info("polymarket_ws_recovered, stopping REST poll")
                break

            tokens = list(_poll_subscribed_tokens)
            if not tokens or _polymarket_manager.active_count == 0:
                continue

            # Cycle through tokens instead of always grabbing the first N
            num_tokens = len(tokens)
            _poll_index = _poll_index % num_tokens
            # Fetch up to 15 concurrent tokens per cycle
            batch_size = min(15, num_tokens)
            end_index = _poll_index + batch_size
            
            if end_index > num_tokens:
                batch = tokens[_poll_index:num_tokens] + tokens[0:(end_index - num_tokens)]
            else:
                batch = tokens[_poll_index:end_index]
                
            _poll_index = end_index % num_tokens

            for tid in batch:
                try:
                    book = await client.get_orderbook(tid)
                    d = book.model_dump()
                    d["asset_id"] = tid
                    await _broadcast_poly("book", d, tid)
                    ltp = d.get("last_trade_price", "")
                    if ltp:
                        await _broadcast_poly(
                            "last_trade",
                            {"asset_id": tid, "price": ltp},
                            tid,
                        )
                except Exception:
                    logger.debug(
                        "polymarket_rest_poll_orderbook_failed",
                        asset_id=tid,
                        exc_info=True,
                    )

    except asyncio.CancelledError:
        pass
    finally:
        await client.close()
        logger.info("polymarket_rest_poll_stopped")


def _ensure_poll_fallback() -> None:
    """Start the REST polling task if WS is not connected."""
    global _poll_task
    if _poly_ws_client is not None and _poly_ws_client.is_connected:
        return
    if _poll_task is not None and not _poll_task.done():
        return
    _poll_task = asyncio.create_task(
        _poll_orderbooks(), name="polymarket-rest-poll"
    )


@router.websocket("/api/v1/ws/polymarket")
async def ws_polymarket(ws: WebSocket) -> None:
    """Real-time Polymarket data WebSocket.

    Client messages (JSON):
        ``{"action": "subscribe", "token_ids": ["abc123..."]}``
        ``{"action": "unsubscribe", "token_ids": ["abc123..."]}``

    Server pushes:
        ``{"type": "book", "data": {...}}``
        ``{"type": "price_change", "data": {...}}``
        ``{"type": "last_trade", "data": {...}}``
    """
    await _polymarket_manager.connect(ws)
    logger.info("ws_polymarket_connected", connections=_polymarket_manager.active_count)

    poly_ws = await _ensure_poly_ws()

    try:
        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=60.0)
            except TimeoutError:
                try:
                    await ws.send_json({"type": "ping", "timestamp": int(time.time() * 1000)})
                except Exception:
                    break
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            action = msg.get("action")
            token_ids: list[str] = msg.get("token_ids", [])

            if action == "subscribe" and token_ids:
                for tid in token_ids:
                    _polymarket_manager.subscribe(ws, f"poly:{tid}")
                    _poll_subscribed_tokens.add(tid)

                if poly_ws is not None:
                    try:
                        await poly_ws.subscribe_market(token_ids)
                    except Exception:
                        logger.warning("poly_ws_subscribe_failed", exc_info=True)
                else:
                    _ensure_poll_fallback()

                await ws.send_json({
                    "type": "subscribed",
                    "token_ids": token_ids,
                    "timestamp": int(time.time() * 1000),
                })
            elif action == "unsubscribe" and token_ids:
                for tid in token_ids:
                    _polymarket_manager.unsubscribe(ws, f"poly:{tid}")
                    _poll_subscribed_tokens.discard(tid)
                await ws.send_json({
                    "type": "unsubscribed",
                    "token_ids": token_ids,
                    "timestamp": int(time.time() * 1000),
                })
            else:
                await ws.send_json({"type": "error", "message": f"Unknown action: {action}"})

    except WebSocketDisconnect:
        pass
    finally:
        _polymarket_manager.disconnect(ws)
        logger.info("ws_polymarket_disconnected", connections=_polymarket_manager.active_count)
