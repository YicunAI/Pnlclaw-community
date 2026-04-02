"""Binance User Data Stream client for private account events.

Subscribes to real-time order updates, balance changes, and account position
events via the Binance WebSocket API.

Authentication method (recommended by Binance since 2026):
    - Connect to ``wss://ws-api.binance.com:443/ws-api/v3``
    - ``session.logon`` with Ed25519 or HMAC-SHA256 signed request
    - ``userDataStream.subscribe`` to start receiving events

Legacy fallback (listenKey via REST - deprecated but still functional):
    - ``POST /api/v3/userDataStream`` → listenKey
    - Connect to ``wss://stream.binance.com:9443/ws/{listenKey}``
    - ``PUT /api/v3/userDataStream`` every 30 min to keep alive
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from collections.abc import Callable
from typing import Any

import websockets
import websockets.asyncio.client

from pnlclaw_exchange.base.stall_watchdog import StallTimeoutMeta, StallWatchdog
from pnlclaw_exchange.base.ws_client import BaseWSClient
from pnlclaw_exchange.normalizers.symbol import SymbolNormalizer
from pnlclaw_exchange.types import WSClientConfig
from pnlclaw_types.trading import (
    BalanceUpdate,
    ExchangeOrderUpdate,
    OrderSide,
)

logger = logging.getLogger(__name__)

BINANCE_WS_API_URL = "wss://ws-api.binance.com:443/ws-api/v3"
BINANCE_STREAM_URL = "wss://stream.binance.com:9443/ws"
BINANCE_VISION_STREAM_URL = "wss://data-stream.binance.vision/ws"

EXCHANGE = "binance"


class BinanceUserDataNormalizer:
    """Normalize Binance User Data Stream events into unified models."""

    def __init__(self, symbol_normalizer: SymbolNormalizer) -> None:
        self._symbols = symbol_normalizer

    def normalize_execution_report(self, data: dict[str, Any]) -> ExchangeOrderUpdate:
        raw_symbol = data.get("s", "")
        symbol = self._symbols.to_unified(EXCHANGE, raw_symbol)
        side_str = data.get("S", "BUY").upper()
        side = OrderSide.BUY if side_str == "BUY" else OrderSide.SELL

        cumulative_qty = float(data.get("z", "0"))
        cumulative_quote = float(data.get("Z", "0"))
        avg_price = (cumulative_quote / cumulative_qty) if cumulative_qty > 0 else 0.0

        return ExchangeOrderUpdate(
            exchange=EXCHANGE,
            exchange_order_id=str(data.get("i", "")),
            client_order_id=data.get("c"),
            symbol=symbol,
            side=side,
            order_type=data.get("o", "UNKNOWN"),
            status=data.get("X", "UNKNOWN"),
            quantity=float(data.get("q", "0")),
            filled_quantity=cumulative_qty,
            avg_fill_price=avg_price,
            last_fill_price=float(data.get("L", "0")),
            last_fill_quantity=float(data.get("l", "0")),
            commission=float(data.get("n", "0")),
            commission_asset=data.get("N"),
            timestamp=int(data.get("E", 0)),
            raw=data,
        )

    def normalize_account_position(self, data: dict[str, Any]) -> list[BalanceUpdate]:
        ts = int(data.get("E", 0))
        balances = data.get("B", [])
        result: list[BalanceUpdate] = []
        for b in balances:
            result.append(
                BalanceUpdate(
                    exchange=EXCHANGE,
                    asset=b.get("a", ""),
                    free=float(b.get("f", "0")),
                    locked=float(b.get("l", "0")),
                    timestamp=ts,
                )
            )
        return result

    def normalize_balance_update(self, data: dict[str, Any]) -> BalanceUpdate:
        return BalanceUpdate(
            exchange=EXCHANGE,
            asset=data.get("a", ""),
            free=float(data.get("d", "0")),
            locked=0.0,
            timestamp=int(data.get("E", 0)),
        )


class BinanceUserDataClient(BaseWSClient):
    """Binance private WebSocket client for account/order/balance events.

    Supports two authentication modes:
    1. WebSocket API session.logon (Ed25519/HMAC) — preferred
    2. Legacy listenKey via REST (deprecated fallback)
    """

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        url: str = BINANCE_WS_API_URL,
        symbol_normalizer: SymbolNormalizer | None = None,
        stall_timeout_s: float = 60.0,
        on_order_update: Callable[[ExchangeOrderUpdate], Any] | None = None,
        on_balance_update: Callable[[list[BalanceUpdate]], Any] | None = None,
        on_balance_delta: Callable[[BalanceUpdate], Any] | None = None,
        on_stall: Callable[[StallTimeoutMeta], Any] | None = None,
        **kwargs: Any,
    ) -> None:
        config = WSClientConfig(url=url, exchange=EXCHANGE, stall_timeout_s=stall_timeout_s)
        super().__init__(config, **kwargs)

        self._api_key = api_key
        self._api_secret = api_secret
        self._normalizer = BinanceUserDataNormalizer(symbol_normalizer or SymbolNormalizer())
        self._ws: websockets.asyncio.client.ClientConnection | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self._request_id: int = 0
        self._authenticated: bool = False

        self._stall_watchdog = StallWatchdog(
            timeout_s=stall_timeout_s,
            on_timeout=on_stall or self._default_stall_handler,
            label="binance-userdata-stall",
        )

        self.on_order_update = on_order_update
        self.on_balance_update = on_balance_update
        self.on_balance_delta = on_balance_delta

    # ------------------------------------------------------------------
    # BaseWSClient implementation
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        logger.info("Connecting to Binance User Data WS: %s", self._config.url)
        self._ws = await websockets.asyncio.client.connect(self._config.url)
        await self._dispatch_connect()
        await self._stall_watchdog.start()
        self._receive_task = asyncio.create_task(self._receive_loop(), name="binance-userdata-recv")

    async def subscribe(self, streams: list[str]) -> None:
        """Authenticate and subscribe to user data stream.

        For the WebSocket API path, ``streams`` is ignored — we call
        ``session.logon`` followed by ``userDataStream.subscribe``.
        """
        if self._ws is None:
            return

        if not self._authenticated:
            await self._session_logon()
            self._authenticated = True

        req_id = self._next_id()
        msg = {
            "id": str(req_id),
            "method": "userDataStream.subscribe",
        }
        await self._ws.send(json.dumps(msg))
        self._subscriptions.add("userDataStream")
        self._stall_watchdog.arm()
        logger.info("Subscribed to Binance user data stream")

    async def unsubscribe(self, streams: list[str]) -> None:
        if self._ws is None:
            return
        msg = {
            "id": str(self._next_id()),
            "method": "userDataStream.unsubscribe",
        }
        await self._ws.send(json.dumps(msg))
        self._subscriptions.discard("userDataStream")
        logger.info("Unsubscribed from Binance user data stream")

    async def close(self) -> None:
        self._stall_watchdog.stop()
        self._authenticated = False

        if self._receive_task is not None and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None

        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        await self._dispatch_disconnect(code=1000, reason="client close")

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def _session_logon(self) -> None:
        """Authenticate using HMAC-SHA256 via session.logon."""
        timestamp = int(time.time() * 1000)
        params: dict[str, Any] = {
            "apiKey": self._api_key,
            "timestamp": timestamp,
        }
        query_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        signature = hmac.new(self._api_secret.encode(), query_str.encode(), hashlib.sha256).hexdigest()
        params["signature"] = signature

        msg = {
            "id": str(self._next_id()),
            "method": "session.logon",
            "params": params,
        }
        await self._ws.send(json.dumps(msg))  # type: ignore[union-attr]
        logger.info("Sent session.logon to Binance WS API")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _receive_loop(self) -> None:
        if self._ws is None:
            return

        try:
            async for raw in self._ws:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from Binance user stream: %s", raw[:200])
                    continue
                await self._route_message(data)
        except websockets.ConnectionClosed as exc:
            logger.info("Binance user data WS closed: %s", exc)
            await self._dispatch_disconnect(
                code=exc.code if hasattr(exc, "code") else 1006,
                reason=str(exc),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Error in Binance user data receive loop: %s", exc)
            await self._dispatch_error(exc)

    async def _route_message(self, data: dict[str, Any]) -> None:
        self._stall_watchdog.touch()

        # API responses (session.logon result, subscribe result, etc.)
        if "id" in data and "status" in data:
            status = data.get("status")
            if status and status != 200:
                logger.error("Binance WS API error: %s", data)
                await self._dispatch_error(RuntimeError(f"Binance WS API error: {data}"))
            return

        # User data stream event envelope: {"subscriptionId": N, "event": {...}}
        event = data.get("event", data)
        event_type = event.get("e")

        await self._dispatch_message(event)

        if event_type == "executionReport":
            order_update = self._normalizer.normalize_execution_report(event)
            await self._invoke(self.on_order_update, order_update)

        elif event_type == "outboundAccountPosition":
            balance_updates = self._normalizer.normalize_account_position(event)
            await self._invoke(self.on_balance_update, balance_updates)

        elif event_type == "balanceUpdate":
            delta = self._normalizer.normalize_balance_update(event)
            await self._invoke(self.on_balance_delta, delta)

        elif event_type == "eventStreamTerminated":
            logger.warning("Binance user data stream terminated, will reconnect")
            if self._ws is not None:
                try:
                    await self._ws.close()
                except Exception:
                    pass

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _default_stall_handler(self, meta: StallTimeoutMeta) -> None:
        logger.warning(
            "Binance user data stall (idle %.1fs). Closing for reconnect.",
            meta.idle_s,
        )
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
