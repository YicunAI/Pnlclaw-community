"""Binance WebSocket client for public market data streams.

Connects to Binance's public WebSocket API and provides typed callbacks
for ticker, trade, kline, and depth (L2) events. No API key required.
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
from pnlclaw_exchange.exchanges.binance.normalizer import (
    BinanceDepthDelta,
    BinanceNormalizer,
)
from pnlclaw_exchange.normalizers.symbol import SymbolNormalizer
from pnlclaw_exchange.types import WSClientConfig
from pnlclaw_types.derivatives import FundingRateEvent, LiquidationEvent
from pnlclaw_types.market import KlineEvent, TickerEvent, TradeEvent

logger = logging.getLogger(__name__)

DEFAULT_BINANCE_WS_URL = "wss://data-stream.binance.vision/ws"


class BinanceWSClient(BaseWSClient):
    """Binance WebSocket client for public market data streams.

    Contract:
        - Connects to ``wss://stream.binance.com:9443/ws``.
        - Subscribes via JSON messages: ``{"method":"SUBSCRIBE", ...}``.
        - Supports ticker, kline, trade, and depth (L2) streams.
        - Delegates message parsing to :class:`BinanceNormalizer`.
        - Integrates :class:`StallWatchdog` for data stall detection.
        - No API key required for public streams.
    """

    def __init__(
        self,
        *,
        url: str = DEFAULT_BINANCE_WS_URL,
        proxy_url: str | None = None,
        symbol_normalizer: SymbolNormalizer | None = None,
        stall_timeout_s: float = 30.0,
        on_ticker: Callable[[TickerEvent], Any] | None = None,
        on_trade: Callable[[TradeEvent], Any] | None = None,
        on_kline: Callable[[KlineEvent], Any] | None = None,
        on_depth_update: Callable[[BinanceDepthDelta], Any] | None = None,
        on_liquidation: Callable[[LiquidationEvent], Any] | None = None,
        on_funding_rate: Callable[[FundingRateEvent], Any] | None = None,
        on_stall: Callable[[StallTimeoutMeta], Any] | None = None,
        **kwargs: Any,
    ) -> None:
        config = WSClientConfig(url=url, exchange="binance", proxy_url=proxy_url)
        super().__init__(config, **kwargs)

        self._symbol_normalizer = symbol_normalizer or SymbolNormalizer()
        self._normalizer = BinanceNormalizer(self._symbol_normalizer)
        self._ws: websockets.asyncio.client.ClientConnection | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self._request_id: int = 0

        self._stall_watchdog = StallWatchdog(
            timeout_s=stall_timeout_s,
            on_timeout=on_stall or self._default_stall_handler,
            label="binance-ws-stall",
        )

        self.on_ticker = on_ticker
        self.on_trade = on_trade
        self.on_kline = on_kline
        self.on_depth_update = on_depth_update
        self.on_liquidation = on_liquidation
        self.on_funding_rate = on_funding_rate

    # ------------------------------------------------------------------
    # BaseWSClient implementation
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open WebSocket connection to Binance."""
        proxy = self._config.proxy_url or None
        logger.info("Connecting to Binance WS: %s (proxy=%s)", self._config.url, proxy or "none")
        self._ws = await websockets.asyncio.client.connect(
            self._config.url,
            proxy=proxy,
            ping_interval=30,
            ping_timeout=60,
        )
        await self._dispatch_connect()
        await self._stall_watchdog.start()
        if self._subscriptions:
            self._stall_watchdog.arm()
        self._receive_task = asyncio.create_task(self._receive_loop(), name="binance-ws-recv")

    async def subscribe(self, streams: list[str]) -> None:
        """Subscribe to Binance streams via JSON subscription message.

        Args:
            streams: List of stream names in Binance format, e.g.
                ``["btcusdt@ticker", "btcusdt@kline_1h"]``.
        """
        if not streams:
            return
        self._subscriptions.update(streams)
        if self._ws is None:
            logger.info("Queued %d Binance streams (WS not connected yet)", len(streams))
            return
        msg = {
            "method": "SUBSCRIBE",
            "params": streams,
            "id": self._next_id(),
        }
        await self._ws.send(json.dumps(msg))
        self._stall_watchdog.arm()
        logger.info("Subscribed to %d Binance streams", len(streams))

    async def unsubscribe(self, streams: list[str]) -> None:
        """Unsubscribe from Binance streams."""
        if not streams or self._ws is None:
            return
        self._subscriptions -= set(streams)
        msg = {
            "method": "UNSUBSCRIBE",
            "params": streams,
            "id": self._next_id(),
        }
        await self._ws.send(json.dumps(msg))
        logger.info("Unsubscribed from %d Binance streams", len(streams))

    async def close(self) -> None:
        """Close the WebSocket connection and cancel the receive loop."""
        self._stall_watchdog.stop()

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
    # Convenience subscription methods
    # ------------------------------------------------------------------

    async def subscribe_ticker(self, symbols: list[str]) -> None:
        """Subscribe to 24hr ticker streams for the given symbols.

        Args:
            symbols: Binance symbols, e.g. ``["btcusdt", "ethusdt"]``.
        """
        streams = [self.stream_name(s, "ticker") for s in symbols]
        await self.subscribe(streams)

    async def subscribe_kline(self, symbols: list[str], interval: str) -> None:
        """Subscribe to kline streams for the given symbols and interval.

        Args:
            symbols: Binance symbols.
            interval: Kline interval, e.g. ``"1m"``, ``"1h"``.
        """
        streams = [self.stream_name(s, "kline", interval=interval) for s in symbols]
        await self.subscribe(streams)

    async def subscribe_trade(self, symbols: list[str]) -> None:
        """Subscribe to trade streams for the given symbols."""
        streams = [self.stream_name(s, "trade") for s in symbols]
        await self.subscribe(streams)

    async def subscribe_agg_trade(self, symbols: list[str]) -> None:
        """Subscribe to aggregated trade streams (100ms batching).

        Each message groups trades at the same price/side within a 100ms window.
        """
        streams = [self.stream_name(s, "aggTrade") for s in symbols]
        await self.subscribe(streams)

    async def subscribe_depth(self, symbols: list[str]) -> None:
        """Subscribe to depth (L2) streams at 100ms update frequency.

        Args:
            symbols: Binance symbols, e.g. ``["btcusdt"]``.
        """
        streams = [self.stream_name(s, "depth@100ms") for s in symbols]
        await self.subscribe(streams)

    async def subscribe_force_order(self, symbols: list[str] | None = None) -> None:
        """Subscribe to liquidation (forced order) streams.

        Args:
            symbols: If None, subscribes to all-market liquidation stream
                     ``!forceOrder@arr``. Otherwise per-symbol streams.
        """
        if symbols is None:
            await self.subscribe(["!forceOrder@arr"])
        else:
            streams = [self.stream_name(s, "forceOrder") for s in symbols]
            await self.subscribe(streams)

    async def subscribe_mark_price(self, symbols: list[str] | None = None) -> None:
        """Subscribe to mark price streams (includes funding rate).

        Args:
            symbols: If None, subscribes to all-market ``!markPrice@arr@1s``.
                     Otherwise per-symbol ``<symbol>@markPrice@1s``.
        """
        if symbols is None:
            await self.subscribe(["!markPrice@arr@1s"])
        else:
            streams = [self.stream_name(s, "markPrice@1s") for s in symbols]
            await self.subscribe(streams)

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def stream_name(symbol: str, channel: str, *, interval: str | None = None) -> str:
        """Construct a Binance stream name.

        Examples::

            stream_name("btcusdt", "ticker")          → "btcusdt@ticker"
            stream_name("btcusdt", "kline", interval="1h") → "btcusdt@kline_1h"
            stream_name("btcusdt", "depth@100ms")      → "btcusdt@depth@100ms"
        """
        sym = symbol.lower()
        if channel == "kline" and interval:
            return f"{sym}@kline_{interval}"
        return f"{sym}@{channel}"

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _receive_loop(self) -> None:
        """Read messages from WebSocket and route them."""
        if self._ws is None:
            return

        try:
            async for raw in self._ws:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from Binance: %s", raw[:200])
                    continue

                try:
                    await self._route_message(data)
                except Exception as route_exc:
                    logger.debug(
                        "Skipping unprocessable Binance message: %s",
                        route_exc,
                    )
                    continue
        except websockets.ConnectionClosed as exc:
            logger.info("Binance WS connection closed: %s", exc)
            await self._dispatch_disconnect(
                code=exc.code if hasattr(exc, "code") else 1006,
                reason=str(exc),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Error in Binance receive loop: %s", exc)
            await self._dispatch_error(exc)

    async def _route_message(self, data: dict[str, Any] | list[Any]) -> None:
        """Route a parsed message to the appropriate callback."""
        self._stall_watchdog.touch()

        # !markPrice@arr and !forceOrder@arr push JSON arrays
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    await self._route_single(item)
            return

        # Handle combined stream format: {"stream": "...", "data": {...}}
        if "stream" in data and "data" in data:
            payload = data["data"]
            if isinstance(payload, list):
                for item in payload:
                    if isinstance(item, dict):
                        await self._route_single(item)
                return
            data = payload

        await self._route_single(data)

    async def _route_single(self, data: dict[str, Any]) -> None:
        """Route a single parsed message to the appropriate callback."""
        # Skip subscription response messages.
        if "result" in data and "id" in data:
            return

        await self._dispatch_message(data)

        event = self._normalizer.normalize(data)
        if event is None:
            return

        if isinstance(event, TickerEvent):
            await self._invoke(self.on_ticker, event)
        elif isinstance(event, TradeEvent):
            await self._invoke(self.on_trade, event)
        elif isinstance(event, KlineEvent):
            await self._invoke(self.on_kline, event)
        elif isinstance(event, BinanceDepthDelta):
            await self._invoke(self.on_depth_update, event)
        elif isinstance(event, LiquidationEvent):
            await self._invoke(self.on_liquidation, event)
        elif isinstance(event, FundingRateEvent):
            await self._invoke(self.on_funding_rate, event)

    def _next_id(self) -> int:
        """Return an auto-incrementing request ID."""
        self._request_id += 1
        return self._request_id

    async def _default_stall_handler(self, meta: StallTimeoutMeta) -> None:
        """Default stall handler: log and force reconnect by closing WS."""
        logger.warning(
            "Binance WS stall detected (idle %.1fs). Closing for reconnect.",
            meta.idle_s,
        )
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
