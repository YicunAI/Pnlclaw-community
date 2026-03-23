"""OKX Private WebSocket client for account, order, and position events.

Connects to ``wss://ws.okx.com:8443/ws/v5/private`` with HMAC-SHA256 login.

Subscribes to:
- ``orders`` channel — order status changes (new, partial, filled, canceled)
- ``account`` channel — balance changes
- ``positions`` channel — position updates

Docs: https://www.okx.com/docs-v5/en/#order-book-trading-trade-ws-order-channel
"""

from __future__ import annotations

import asyncio
import base64
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
from pnlclaw_exchange.types import WSClientConfig
from pnlclaw_types.trading import (
    BalanceUpdate,
    ExchangeOrderUpdate,
    OrderSide,
)

logger = logging.getLogger(__name__)

DEFAULT_OKX_PRIVATE_URL = "wss://ws.okx.com:8443/ws/v5/private"
EXCHANGE = "okx"


class OKXPrivateNormalizer:
    """Normalize OKX private channel events into unified models."""

    @staticmethod
    def normalize_order(item: dict[str, Any]) -> ExchangeOrderUpdate:
        side_raw = item.get("side", "buy").lower()
        side = OrderSide.BUY if side_raw == "buy" else OrderSide.SELL
        inst_id = item.get("instId", "")
        symbol = inst_id.replace("-", "/")

        fill_sz = float(item.get("accFillSz", "0") or "0")
        avg_px_str = item.get("avgPx", "")
        avg_px = float(avg_px_str) if avg_px_str else 0.0

        last_px_str = item.get("fillPx", "")
        last_qty_str = item.get("fillSz", "")
        fee_str = item.get("fee", "0") or "0"

        status_map = {
            "live": "NEW",
            "partially_filled": "PARTIALLY_FILLED",
            "filled": "FILLED",
            "canceled": "CANCELED",
            "cancelled": "CANCELED",
        }
        okx_state = item.get("state", "live")

        return ExchangeOrderUpdate(
            exchange=EXCHANGE,
            exchange_order_id=item.get("ordId", ""),
            client_order_id=item.get("clOrdId") or None,
            symbol=symbol,
            side=side,
            order_type=item.get("ordType", ""),
            status=status_map.get(okx_state, okx_state.upper()),
            quantity=float(item.get("sz", "0") or "0"),
            filled_quantity=fill_sz,
            avg_fill_price=avg_px,
            last_fill_price=float(last_px_str) if last_px_str else 0.0,
            last_fill_quantity=float(last_qty_str) if last_qty_str else 0.0,
            commission=abs(float(fee_str)),
            commission_asset=item.get("feeCcy"),
            timestamp=int(item.get("uTime", "0") or "0"),
            raw=item,
        )

    @staticmethod
    def normalize_account(item: dict[str, Any], ts: int) -> list[BalanceUpdate]:
        details = item.get("details", [])
        result: list[BalanceUpdate] = []
        for d in details:
            result.append(BalanceUpdate(
                exchange=EXCHANGE,
                asset=d.get("ccy", ""),
                free=float(d.get("availBal", "0") or "0"),
                locked=float(d.get("frozenBal", "0") or "0"),
                timestamp=ts,
            ))
        return result


class OKXPrivateWSClient(BaseWSClient):
    """OKX private WebSocket client for orders, account, and positions.

    Authentication flow:
        1. Connect to ``/ws/v5/private``
        2. Send login message with HMAC-SHA256 signature
        3. Subscribe to ``orders``, ``account``, ``positions`` channels
    """

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        passphrase: str,
        url: str = DEFAULT_OKX_PRIVATE_URL,
        stall_timeout_s: float = 60.0,
        on_order_update: Callable[[ExchangeOrderUpdate], Any] | None = None,
        on_balance_update: Callable[[list[BalanceUpdate]], Any] | None = None,
        on_stall: Callable[[StallTimeoutMeta], Any] | None = None,
        **kwargs: Any,
    ) -> None:
        config = WSClientConfig(url=url, exchange=EXCHANGE, stall_timeout_s=stall_timeout_s)
        super().__init__(config, **kwargs)

        self._api_key = api_key
        self._api_secret = api_secret
        self._passphrase = passphrase
        self._normalizer = OKXPrivateNormalizer()

        self._ws: websockets.asyncio.client.ClientConnection | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self._authenticated: bool = False

        self._stall_watchdog = StallWatchdog(
            timeout_s=stall_timeout_s,
            on_timeout=on_stall or self._default_stall_handler,
            label="okx-private-stall",
        )

        self.on_order_update = on_order_update
        self.on_balance_update = on_balance_update

    # ------------------------------------------------------------------
    # BaseWSClient implementation
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        logger.info("Connecting to OKX private WS: %s", self._config.url)
        self._ws = await websockets.asyncio.client.connect(self._config.url)
        await self._dispatch_connect()
        await self._stall_watchdog.start()
        self._receive_task = asyncio.create_task(
            self._receive_loop(), name="okx-private-recv"
        )

    async def subscribe(self, streams: list[str]) -> None:
        """Authenticate and subscribe to private channels.

        ``streams`` is ignored for the initial subscription — we subscribe
        to all relevant private channels (orders, account, positions).
        """
        if self._ws is None:
            return

        if not self._authenticated:
            await self._login()
            await asyncio.sleep(0.5)

        args = [
            {"channel": "orders", "instType": "ANY"},
            {"channel": "account"},
            {"channel": "positions", "instType": "ANY"},
        ]
        msg = {"op": "subscribe", "args": args}
        await self._ws.send(json.dumps(msg))

        self._subscriptions.update(["orders", "account", "positions"])
        self._stall_watchdog.arm()
        logger.info("Subscribed to OKX private channels: orders, account, positions")

    async def unsubscribe(self, streams: list[str]) -> None:
        if self._ws is None:
            return

        args = [{"channel": ch} for ch in streams]
        msg = {"op": "unsubscribe", "args": args}
        await self._ws.send(json.dumps(msg))
        self._subscriptions -= set(streams)

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

    async def _login(self) -> None:
        """Send OKX login message with HMAC-SHA256 signature.

        Signing: ``timestamp + "GET" + "/users/self/verify"`` → HMAC-SHA256 → Base64
        """
        timestamp = str(int(time.time()))
        prehash = timestamp + "GET" + "/users/self/verify"
        mac = hmac.new(
            self._api_secret.encode(), prehash.encode(), hashlib.sha256
        )
        sign = base64.b64encode(mac.digest()).decode()

        msg = {
            "op": "login",
            "args": [
                {
                    "apiKey": self._api_key,
                    "passphrase": self._passphrase,
                    "timestamp": timestamp,
                    "sign": sign,
                }
            ],
        }
        await self._ws.send(json.dumps(msg))  # type: ignore[union-attr]
        logger.info("Sent login to OKX private WS")

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
                    logger.warning("Invalid JSON from OKX private: %s", raw[:200])
                    continue
                await self._route_message(data)
        except websockets.ConnectionClosed as exc:
            logger.info("OKX private WS closed: %s", exc)
            self._authenticated = False
            await self._dispatch_disconnect(
                code=getattr(exc, "code", 1006), reason=str(exc)
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Error in OKX private receive loop: %s", exc)
            await self._dispatch_error(exc)

    async def _route_message(self, data: dict[str, Any]) -> None:
        self._stall_watchdog.touch()

        # Login response
        if "event" in data:
            event = data["event"]
            if event == "login":
                code = data.get("code", "0")
                if code == "0":
                    self._authenticated = True
                    logger.info("OKX private WS login successful")
                else:
                    logger.error("OKX private WS login failed: %s", data.get("msg", ""))
                    await self._dispatch_error(
                        RuntimeError(f"OKX login failed: {data.get('msg', '')}")
                    )
            return

        # Subscribe/unsubscribe ack
        if "op" in data:
            return

        arg = data.get("arg", {})
        channel = arg.get("channel", "")
        items = data.get("data", [])

        if not items:
            return

        await self._dispatch_message(data)

        if channel == "orders":
            for item in items:
                order_update = self._normalizer.normalize_order(item)
                await self._invoke(self.on_order_update, order_update)

        elif channel == "account":
            ts = int(time.time() * 1000)
            for item in items:
                balance_updates = self._normalizer.normalize_account(item, ts)
                await self._invoke(self.on_balance_update, balance_updates)

        elif channel == "positions":
            pass  # Position data available in raw dispatch_message

    async def _default_stall_handler(self, meta: StallTimeoutMeta) -> None:
        logger.warning(
            "OKX private WS stall (idle %.1fs). Closing for reconnect.",
            meta.idle_s,
        )
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
