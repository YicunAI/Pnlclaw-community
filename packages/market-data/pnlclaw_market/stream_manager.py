"""Stream lifecycle manager: manages WS subscriptions with reference counting.

Tracks active symbol/stream-type combinations, ensures only one WS stream
per unique subscription, and supports automatic resubscription after reconnect.
"""

from __future__ import annotations

import logging
import threading
from enum import Enum

from pnlclaw_exchange import BinanceL2Manager, BinanceWSClient

logger = logging.getLogger(__name__)


class StreamType(str, Enum):
    """Types of market data streams."""

    TICKER = "ticker"
    KLINE = "kline"
    DEPTH = "depth"


class _StreamRef:
    """Reference counter for a single stream subscription."""

    __slots__ = ("count",)

    def __init__(self) -> None:
        self.count: int = 0


class StreamManager:
    """Manages WS subscription lifecycle with reference counting.

    Multiple consumers can subscribe to the same symbol/stream-type.
    Only one actual WS stream is opened per unique (symbol, stream_type) pair.
    The stream is closed when the last consumer unsubscribes.

    Args:
        ws_client: The Binance WS client for subscribing/unsubscribing.
        l2_manager: The L2 orderbook manager for depth streams.
        kline_interval: Default kline interval (e.g. ``"1h"``).
    """

    def __init__(
        self,
        ws_client: BinanceWSClient,
        l2_manager: BinanceL2Manager,
        kline_interval: str = "1h",
    ) -> None:
        self._ws_client = ws_client
        self._l2_manager = l2_manager
        self._kline_interval = kline_interval
        self._refs: dict[tuple[str, StreamType], _StreamRef] = {}
        self._lock = threading.Lock()

    async def start_stream(self, symbol: str, stream_type: StreamType) -> None:
        """Start (or increment reference to) a stream for *symbol*.

        If this is the first consumer, the actual WS subscription is opened.

        Args:
            symbol: Normalized trading pair, e.g. ``"BTC/USDT"``.
            stream_type: Type of stream to subscribe.
        """
        key = (symbol, stream_type)
        subscribe_needed = False

        with self._lock:
            if key not in self._refs:
                self._refs[key] = _StreamRef()
            ref = self._refs[key]
            if ref.count == 0:
                subscribe_needed = True
            ref.count += 1

        if subscribe_needed:
            await self._subscribe(symbol, stream_type)
            logger.info("Started stream %s for %s (ref=1)", stream_type.value, symbol)
        else:
            logger.debug(
                "Incremented ref for stream %s/%s (ref=%d)",
                symbol,
                stream_type.value,
                ref.count,
            )

    async def stop_stream(self, symbol: str, stream_type: StreamType) -> None:
        """Stop (or decrement reference to) a stream for *symbol*.

        The actual WS unsubscription happens only when the last consumer leaves.
        No-op if the stream is not currently active.

        Args:
            symbol: Normalized trading pair.
            stream_type: Type of stream to unsubscribe.
        """
        key = (symbol, stream_type)
        unsubscribe_needed = False

        with self._lock:
            ref = self._refs.get(key)
            if ref is None or ref.count <= 0:
                return
            ref.count -= 1
            if ref.count == 0:
                unsubscribe_needed = True
                del self._refs[key]

        if unsubscribe_needed:
            await self._unsubscribe(symbol, stream_type)
            logger.info("Stopped stream %s for %s", stream_type.value, symbol)

    def active_symbols(self) -> list[str]:
        """Return a list of symbols with at least one active stream."""
        with self._lock:
            return sorted({sym for (sym, st), ref in self._refs.items() if ref.count > 0})

    def active_streams(self) -> list[tuple[str, StreamType]]:
        """Return all active (symbol, stream_type) pairs."""
        with self._lock:
            return [(sym, st) for (sym, st), ref in self._refs.items() if ref.count > 0]

    def ref_count(self, symbol: str, stream_type: StreamType) -> int:
        """Return the current reference count for a stream."""
        with self._lock:
            ref = self._refs.get((symbol, stream_type))
            return ref.count if ref else 0

    async def resubscribe_all(self) -> None:
        """Re-subscribe all active streams after a reconnection.

        Called by the service after the ReconnectManager restores the WS connection.
        """
        with self._lock:
            active = [(sym, st) for (sym, st), ref in self._refs.items() if ref.count > 0]

        for symbol, stream_type in active:
            try:
                await self._subscribe(symbol, stream_type)
                logger.info("Resubscribed stream %s for %s", stream_type.value, symbol)
            except Exception:
                logger.exception("Failed to resubscribe %s for %s", stream_type.value, symbol)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _subscribe(self, symbol: str, stream_type: StreamType) -> None:
        """Issue the actual WS subscription."""
        binance_symbols = [symbol.replace("/", "").lower()]

        if stream_type == StreamType.TICKER:
            await self._ws_client.subscribe_ticker(binance_symbols)
        elif stream_type == StreamType.KLINE:
            await self._ws_client.subscribe_kline(binance_symbols, self._kline_interval)
        elif stream_type == StreamType.DEPTH:
            await self._ws_client.subscribe_depth(binance_symbols)

    async def _unsubscribe(self, symbol: str, stream_type: StreamType) -> None:
        """Issue the actual WS unsubscription."""
        binance_symbol = symbol.replace("/", "").lower()

        if stream_type == StreamType.TICKER:
            stream = f"{binance_symbol}@ticker"
        elif stream_type == StreamType.KLINE:
            stream = f"{binance_symbol}@kline_{self._kline_interval}"
        elif stream_type == StreamType.DEPTH:
            stream = f"{binance_symbol}@depth@100ms"
        else:
            return

        await self._ws_client.unsubscribe([stream])
