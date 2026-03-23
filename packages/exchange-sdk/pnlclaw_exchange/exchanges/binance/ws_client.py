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

from pnlclaw_exchange.base.ws_client import BaseWSClient
from pnlclaw_exchange.exchanges.binance.normalizer import (
    BinanceDepthDelta,
    BinanceNormalizer,
)
from pnlclaw_exchange.normalizers.symbol import SymbolNormalizer
from pnlclaw_exchange.types import WSClientConfig
from pnlclaw_types.market import KlineEvent, TickerEvent, TradeEvent

logger = logging.getLogger(__name__)

DEFAULT_BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"


class BinanceWSClient(BaseWSClient):
    """Binance WebSocket client for public market data streams.

    Contract:
        - Connects to ``wss://stream.binance.com:9443/ws``.
        - Subscribes via JSON messages: ``{"method":"SUBSCRIBE", ...}``.
        - Supports ticker, kline, trade, and depth (L2) streams.
        - Delegates message parsing to :class:`BinanceNormalizer`.
        - No API key required for public streams.
    """

    def __init__(
        self,
        *,
        url: str = DEFAULT_BINANCE_WS_URL,
        symbol_normalizer: SymbolNormalizer | None = None,
        on_ticker: Callable[[TickerEvent], Any] | None = None,
        on_trade: Callable[[TradeEvent], Any] | None = None,
        on_kline: Callable[[KlineEvent], Any] | None = None,
        on_depth_update: Callable[[BinanceDepthDelta], Any] | None = None,
        **kwargs: Any,
    ) -> None:
        config = WSClientConfig(url=url, exchange="binance")
        super().__init__(config, **kwargs)

        self._symbol_normalizer = symbol_normalizer or SymbolNormalizer()
        self._normalizer = BinanceNormalizer(self._symbol_normalizer)
        self._ws: websockets.asyncio.client.ClientConnection | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self._request_id: int = 0

        # Typed callbacks for normalized events.
        self.on_ticker = on_ticker
        self.on_trade = on_trade
        self.on_kline = on_kline
        self.on_depth_update = on_depth_update

    # ------------------------------------------------------------------
    # BaseWSClient implementation
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open WebSocket connection to Binance."""
        logger.info("Connecting to Binance WS: %s", self._config.url)
        self._ws = await websockets.asyncio.client.connect(self._config.url)
        await self._dispatch_connect()
        self._receive_task = asyncio.create_task(
            self._receive_loop(), name="binance-ws-recv"
        )

    async def subscribe(self, streams: list[str]) -> None:
        """Subscribe to Binance streams via JSON subscription message.

        Args:
            streams: List of stream names in Binance format, e.g.
                ``["btcusdt@ticker", "btcusdt@kline_1h"]``.
        """
        if not streams or self._ws is None:
            return
        self._subscriptions.update(streams)
        msg = {
            "method": "SUBSCRIBE",
            "params": streams,
            "id": self._next_id(),
        }
        await self._ws.send(json.dumps(msg))
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

    async def subscribe_depth(self, symbols: list[str]) -> None:
        """Subscribe to depth (L2) streams at 100ms update frequency.

        Args:
            symbols: Binance symbols, e.g. ``["btcusdt"]``.
        """
        streams = [self.stream_name(s, "depth@100ms") for s in symbols]
        await self.subscribe(streams)

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def stream_name(
        symbol: str, channel: str, *, interval: str | None = None
    ) -> str:
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

                await self._route_message(data)
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

    async def _route_message(self, data: dict[str, Any]) -> None:
        """Route a parsed message to the appropriate callback."""
        # Handle combined stream format: {"stream": "...", "data": {...}}
        if "stream" in data and "data" in data:
            data = data["data"]

        # Skip subscription response messages.
        if "result" in data and "id" in data:
            return

        # Dispatch to raw callback.
        await self._dispatch_message(data)

        # Normalize and dispatch typed callback.
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

    def _next_id(self) -> int:
        """Return an auto-incrementing request ID."""
        self._request_id += 1
        return self._request_id
