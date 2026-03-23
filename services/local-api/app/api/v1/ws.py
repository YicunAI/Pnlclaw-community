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
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.core.dependencies import get_market_service

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["websocket"])


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
        for ws, channels in self._connections.items():
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
            except asyncio.TimeoutError:
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
                for sym in symbols:
                    _market_manager.subscribe(ws, f"market:{sym}")
                await ws.send_json({
                    "type": "subscribed",
                    "symbols": symbols,
                    "timestamp": int(time.time() * 1000),
                })
            elif action == "unsubscribe":
                for sym in symbols:
                    _market_manager.unsubscribe(ws, f"market:{sym}")
                await ws.send_json({
                    "type": "unsubscribed",
                    "symbols": symbols,
                    "timestamp": int(time.time() * 1000),
                })
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
    logger.info("ws_paper_connected", connections=_paper_manager.active_count)
    try:
        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=60.0)
            except asyncio.TimeoutError:
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
                _paper_manager.subscribe(ws, f"paper:{account_id}")
                await ws.send_json({
                    "type": "subscribed",
                    "account_id": account_id,
                    "timestamp": int(time.time() * 1000),
                })
            elif action == "unsubscribe" and account_id:
                _paper_manager.unsubscribe(ws, f"paper:{account_id}")
                await ws.send_json({
                    "type": "unsubscribed",
                    "account_id": account_id,
                    "timestamp": int(time.time() * 1000),
                })
            else:
                await ws.send_json({"type": "error", "message": f"Unknown action: {action}"})

    except WebSocketDisconnect:
        pass
    finally:
        _paper_manager.disconnect(ws)
        logger.info("ws_paper_disconnected", connections=_paper_manager.active_count)


# ---------------------------------------------------------------------------
# Helper for broadcasting from other modules
# ---------------------------------------------------------------------------


async def broadcast_market_event(symbol: str, event_type: str, data: dict[str, Any]) -> None:
    """Push a market event to all WebSocket subscribers of that symbol."""
    await _market_manager.broadcast(
        f"market:{symbol}",
        {"type": event_type, "symbol": symbol, "data": data, "timestamp": int(time.time() * 1000)},
    )


async def broadcast_paper_event(account_id: str, event_type: str, data: dict[str, Any]) -> None:
    """Push a paper trading event to all WebSocket subscribers of that account."""
    await _paper_manager.broadcast(
        f"paper:{account_id}",
        {"type": event_type, "account_id": account_id, "data": data, "timestamp": int(time.time() * 1000)},
    )
