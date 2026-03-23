"""OKX WebSocket client for public market data streams.

Connects to OKX's public WebSocket API v5 and provides typed callbacks
for ticker and kline events. No API key required for public channels.

OKX Protocol:
    - Subscribe: {"op":"subscribe","args":[{"channel":"tickers","instId":"BTC-USDT"}]}
    - Tickers via /ws/v5/public
    - Candlesticks via /ws/v5/business
    - Push: {"arg":{"channel":"tickers","instId":"BTC-USDT"},"data":[{...}]}
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

import websockets
import websockets.asyncio.client

from pnlclaw_exchange.base.stall_watchdog import StallTimeoutMeta, StallWatchdog
from pnlclaw_exchange.base.ws_client import BaseWSClient
from pnlclaw_exchange.exchanges.okx.normalizer import OKXNormalizer
from pnlclaw_exchange.types import WSClientConfig
from pnlclaw_types.market import KlineEvent, TickerEvent

logger = logging.getLogger(__name__)

DEFAULT_OKX_PUBLIC_URL = "wss://ws.okx.com:8443/ws/v5/public"
DEFAULT_OKX_BUSINESS_URL = "wss://ws.okx.com:8443/ws/v5/business"


class OKXWSClient(BaseWSClient):
    """OKX WebSocket client for public market data streams.

    OKX splits public data into two endpoints:
    - ``/ws/v5/public``: tickers, orderbook, trades
    - ``/ws/v5/business``: candlesticks (klines)

    This client manages both connections transparently.
    """

    def __init__(
        self,
        *,
        public_url: str = DEFAULT_OKX_PUBLIC_URL,
        business_url: str = DEFAULT_OKX_BUSINESS_URL,
        kline_interval: str = "1H",
        stall_timeout_s: float = 30.0,
        on_ticker: Callable[[TickerEvent], Any] | None = None,
        on_kline: Callable[[KlineEvent], Any] | None = None,
        on_stall: Callable[[StallTimeoutMeta], Any] | None = None,
        **kwargs: Any,
    ) -> None:
        config = WSClientConfig(url=public_url, exchange="okx")
        super().__init__(config, **kwargs)

        self._public_url = public_url
        self._business_url = business_url
        self._kline_interval = kline_interval
        self._normalizer = OKXNormalizer()

        self._ws_public: websockets.asyncio.client.ClientConnection | None = None
        self._ws_business: websockets.asyncio.client.ClientConnection | None = None
        self._recv_public_task: asyncio.Task[None] | None = None
        self._recv_business_task: asyncio.Task[None] | None = None

        self._stall_watchdog = StallWatchdog(
            timeout_s=stall_timeout_s,
            on_timeout=on_stall or self._default_stall_handler,
            label="okx-ws-stall",
        )

        self.on_ticker = on_ticker
        self.on_kline = on_kline

    async def connect(self) -> None:
        """Open both public and business WebSocket connections."""
        logger.info("Connecting to OKX WS public: %s", self._public_url)
        self._ws_public = await websockets.asyncio.client.connect(self._public_url)

        logger.info("Connecting to OKX WS business: %s", self._business_url)
        self._ws_business = await websockets.asyncio.client.connect(self._business_url)

        await self._dispatch_connect()
        await self._stall_watchdog.start()
        self._stall_watchdog.arm()

        self._recv_public_task = asyncio.create_task(
            self._receive_loop(self._ws_public, "public"), name="okx-ws-public-recv"
        )
        self._recv_business_task = asyncio.create_task(
            self._receive_loop(self._ws_business, "business"), name="okx-ws-business-recv"
        )

    async def subscribe(self, streams: list[str]) -> None:
        """Subscribe to OKX channels.

        Streams should be in format ``"channel:instId"``, e.g. ``"tickers:BTC-USDT"``.
        """
        if not streams:
            return
        self._subscriptions.update(streams)

        public_args: list[dict[str, str]] = []
        business_args: list[dict[str, str]] = []

        for stream in streams:
            channel, inst_id = stream.split(":", 1)
            arg = {"channel": channel, "instId": inst_id}
            if channel.startswith("candle"):
                business_args.append(arg)
            else:
                public_args.append(arg)

        if public_args and self._ws_public:
            await self._ws_public.send(json.dumps({"op": "subscribe", "args": public_args}))
            logger.info("OKX public subscribe: %d channels", len(public_args))

        if business_args and self._ws_business:
            await self._ws_business.send(json.dumps({"op": "subscribe", "args": business_args}))
            logger.info("OKX business subscribe: %d channels", len(business_args))

    async def unsubscribe(self, streams: list[str]) -> None:
        """Unsubscribe from OKX channels."""
        if not streams:
            return
        self._subscriptions -= set(streams)

        public_args: list[dict[str, str]] = []
        business_args: list[dict[str, str]] = []

        for stream in streams:
            channel, inst_id = stream.split(":", 1)
            arg = {"channel": channel, "instId": inst_id}
            if channel.startswith("candle"):
                business_args.append(arg)
            else:
                public_args.append(arg)

        if public_args and self._ws_public:
            await self._ws_public.send(json.dumps({"op": "unsubscribe", "args": public_args}))
        if business_args and self._ws_business:
            await self._ws_business.send(json.dumps({"op": "unsubscribe", "args": business_args}))

    async def close(self) -> None:
        """Close both WebSocket connections."""
        self._stall_watchdog.stop()

        for task in (self._recv_public_task, self._recv_business_task):
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._recv_public_task = None
        self._recv_business_task = None

        for ws in (self._ws_public, self._ws_business):
            if ws is not None:
                try:
                    await ws.close()
                except Exception:
                    pass
        self._ws_public = None
        self._ws_business = None

        await self._dispatch_disconnect(code=1000, reason="client close")

    # Convenience subscription methods

    async def subscribe_ticker(self, inst_ids: list[str]) -> None:
        """Subscribe to ticker channel for given instruments (e.g. ``BTC-USDT``)."""
        streams = [f"tickers:{iid}" for iid in inst_ids]
        await self.subscribe(streams)

    async def subscribe_kline(self, inst_ids: list[str], interval: str | None = None) -> None:
        """Subscribe to candlestick channel.

        Args:
            inst_ids: OKX instrument IDs, e.g. ``["BTC-USDT"]``.
            interval: Candle interval in OKX format, e.g. ``"1H"``, ``"1m"``.
                     Defaults to the interval set during initialization.
        """
        ivl = interval or self._kline_interval
        channel = f"candle{ivl}"
        streams = [f"{channel}:{iid}" for iid in inst_ids]
        await self.subscribe(streams)

    # Internal

    async def _receive_loop(
        self, ws: websockets.asyncio.client.ClientConnection, label: str
    ) -> None:
        """Read messages from one WebSocket and route them."""
        try:
            async for raw in ws:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from OKX %s: %s", label, str(raw)[:200])
                    continue
                await self._route_message(data)
        except websockets.ConnectionClosed as exc:
            logger.info("OKX %s WS connection closed: %s", label, exc)
            await self._dispatch_disconnect(
                code=getattr(exc, "code", 1006), reason=str(exc)
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Error in OKX %s receive loop: %s", label, exc)
            await self._dispatch_error(exc)

    async def _route_message(self, data: dict[str, Any]) -> None:
        """Route a parsed OKX push message to the appropriate callback."""
        self._stall_watchdog.touch()

        # Skip subscribe/unsubscribe acks
        if "event" in data:
            return

        arg = data.get("arg", {})
        channel = arg.get("channel", "")
        inst_id = arg.get("instId", "")
        items = data.get("data", [])

        if not items:
            return

        await self._dispatch_message(data)

        if channel == "tickers":
            for item in items:
                ticker = self._normalizer.normalize_ticker(item, inst_id)
                await self._invoke(self.on_ticker, ticker)
        elif channel.startswith("candle"):
            for candle in items:
                kline = self._normalizer.normalize_candle(candle, inst_id, channel)
                await self._invoke(self.on_kline, kline)

    async def _default_stall_handler(self, meta: StallTimeoutMeta) -> None:
        """Default stall handler: log and force reconnect by closing WS."""
        logger.warning("OKX WS stall detected (idle %.1fs). Closing for reconnect.", meta.idle_s)
        for ws in (self._ws_public, self._ws_business):
            if ws is not None:
                try:
                    await ws.close()
                except Exception:
                    pass
