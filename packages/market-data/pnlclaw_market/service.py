"""Market data main service: manages subscriptions, caching, and data access.

Orchestrates exchange WS clients, stream lifecycle, caching, snapshot storage,
and event dispatch for multiple symbols.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from pnlclaw_exchange import (
    BinanceL2Manager,
    BinanceNormalizer,
    BinanceWSClient,
    ReconnectManager,
)
from pnlclaw_exchange.normalizers.symbol import SymbolNormalizer
from pnlclaw_market.cache import MarketDataCache
from pnlclaw_market.event_bus import EventBus
from pnlclaw_market.snapshot_store import SnapshotStore
from pnlclaw_market.stream_manager import StreamManager, StreamType
from pnlclaw_types.market import (
    KlineEvent,
    OrderBookL2Snapshot,
    TickerEvent,
)

logger = logging.getLogger(__name__)


class MarketDataServiceError(Exception):
    """Base exception for MarketDataService errors."""


class MarketDataServiceNotRunning(MarketDataServiceError):
    """Raised when querying a service that has not been started."""


class MarketDataService:
    """Central market data service managing multi-symbol subscriptions.

    Responsibilities:
        - Start/stop exchange WS connections via ReconnectManager.
        - Add/remove symbol subscriptions (ticker, kline, L2 depth).
        - Cache ticker and kline data for fast retrieval.
        - Maintain L2 orderbook snapshots.
        - Publish events to the internal event bus.

    Args:
        ws_url: Binance WebSocket endpoint.
        rest_url: Binance REST endpoint for L2 snapshot recovery.
        kline_interval: Default kline interval for subscriptions.
        cache_ttl: Cache TTL in seconds.
        cache_max_size: Maximum cache entries.
    """

    def __init__(
        self,
        *,
        ws_url: str = "wss://data-stream.binance.vision/ws",
        rest_url: str = "https://data-api.binance.vision/api/v3/depth",
        kline_interval: str = "1h",
        cache_ttl: float = 60.0,
        cache_max_size: int = 1000,
    ) -> None:
        self._ws_url = ws_url
        self._rest_url = rest_url
        self._kline_interval = kline_interval
        self._running = False

        # Internal components
        self._event_bus = EventBus()
        self._cache = MarketDataCache(ttl_seconds=cache_ttl, max_size=cache_max_size)
        self._snapshot_store = SnapshotStore()
        self._symbol_normalizer = SymbolNormalizer()
        self._normalizer = BinanceNormalizer(self._symbol_normalizer)

        # Exchange clients — created on start()
        self._ws_client: BinanceWSClient | None = None
        self._l2_manager: BinanceL2Manager | None = None
        self._reconnect_manager: ReconnectManager | None = None
        self._stream_manager: StreamManager | None = None
        self._reconnect_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """Whether the service is currently running."""
        return self._running

    @property
    def event_bus(self) -> EventBus:
        """Access the internal event bus for subscribing to market events."""
        return self._event_bus

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the market data service: connect to exchange WS."""
        if self._running:
            return

        self._l2_manager = BinanceL2Manager(
            symbol_normalizer=self._symbol_normalizer,
            on_snapshot=self._on_l2_snapshot,
            rest_url=self._rest_url,
        )

        self._ws_client = BinanceWSClient(
            url=self._ws_url,
            symbol_normalizer=self._symbol_normalizer,
            on_ticker=self._on_ticker,
            on_kline=self._on_kline,
            on_depth_update=self._on_depth_update,
        )

        self._stream_manager = StreamManager(
            ws_client=self._ws_client,
            l2_manager=self._l2_manager,
            kline_interval=self._kline_interval,
        )

        self._reconnect_manager = ReconnectManager(self._ws_client)
        self._reconnect_task = asyncio.create_task(
            self._reconnect_manager.run(), name="market-data-reconnect"
        )

        self._running = True
        logger.info("MarketDataService started")

    async def stop(self) -> None:
        """Gracefully stop the market data service."""
        if not self._running:
            return

        self._running = False

        if self._reconnect_manager is not None:
            await self._reconnect_manager.stop()

        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None

        if self._l2_manager is not None:
            await self._l2_manager.close()

        self._cache.clear()
        self._snapshot_store.clear()

        logger.info("MarketDataService stopped")

    # ------------------------------------------------------------------
    # Symbol management
    # ------------------------------------------------------------------

    async def add_symbol(
        self,
        symbol: str,
        *,
        ticker: bool = True,
        kline: bool = True,
        depth: bool = True,
    ) -> None:
        """Subscribe to market data streams for *symbol*.

        Args:
            symbol: Normalized trading pair, e.g. ``"BTC/USDT"``.
            ticker: Subscribe to ticker stream.
            kline: Subscribe to kline stream.
            depth: Subscribe to L2 depth stream.
        """
        self._ensure_running()
        assert self._stream_manager is not None

        stream_types: list[StreamType] = []
        if ticker:
            stream_types.append(StreamType.TICKER)
        if kline:
            stream_types.append(StreamType.KLINE)
        if depth:
            stream_types.append(StreamType.DEPTH)

        for st in stream_types:
            await self._stream_manager.start_stream(symbol, st)

        # Initialize L2 book if depth requested — gracefully degrade on failure
        l2_active = False
        if depth and self._l2_manager is not None:
            binance_symbol = symbol.replace("/", "").upper()
            try:
                await self._l2_manager.initialize(binance_symbol)
                l2_active = True
            except Exception:
                logger.warning(
                    "L2 depth init failed for %s (REST snapshot unavailable). "
                    "Ticker/kline will still work.",
                    symbol,
                    exc_info=True,
                )

        logger.info(
            "Added symbol %s (ticker=%s, kline=%s, depth=%s, l2_active=%s)",
            symbol, ticker, kline, depth, l2_active,
        )

    async def remove_symbol(self, symbol: str) -> None:
        """Unsubscribe from all streams for *symbol*."""
        self._ensure_running()
        assert self._stream_manager is not None

        for st in StreamType:
            await self._stream_manager.stop_stream(symbol, st)

        self._snapshot_store.remove(symbol)
        logger.info("Removed symbol %s", symbol)

    # ------------------------------------------------------------------
    # Data access
    # ------------------------------------------------------------------

    def get_ticker(self, symbol: str) -> TickerEvent | None:
        """Return the latest cached ticker for *symbol*, or None."""
        self._ensure_running()
        return self._cache.get_ticker(symbol)

    def get_kline(self, symbol: str) -> KlineEvent | None:
        """Return the latest cached kline for *symbol*, or None."""
        self._ensure_running()
        return self._cache.get_kline(symbol)

    def get_orderbook(self, symbol: str) -> OrderBookL2Snapshot | None:
        """Return the latest L2 orderbook snapshot for *symbol*, or None."""
        self._ensure_running()
        return self._snapshot_store.get_snapshot(symbol)

    def get_symbols(self) -> list[str]:
        """Return list of currently subscribed symbols."""
        if self._stream_manager is None:
            return []
        return self._stream_manager.active_symbols()

    # ------------------------------------------------------------------
    # Event subscription convenience
    # ------------------------------------------------------------------

    def on_ticker(self, callback: Callable[[TickerEvent], Any]) -> None:
        """Register a callback for ticker events."""
        self._event_bus.subscribe(TickerEvent, callback)

    def on_kline(self, callback: Callable[[KlineEvent], Any]) -> None:
        """Register a callback for kline events."""
        self._event_bus.subscribe(KlineEvent, callback)

    def on_orderbook(self, callback: Callable[[OrderBookL2Snapshot], Any]) -> None:
        """Register a callback for orderbook snapshot events."""
        self._event_bus.subscribe(OrderBookL2Snapshot, callback)

    # ------------------------------------------------------------------
    # Internal callbacks
    # ------------------------------------------------------------------

    def _on_ticker(self, event: TickerEvent) -> None:
        """Handle incoming ticker event from WS client."""
        self._cache.put_ticker(event.symbol, event)
        self._event_bus.publish(event)

    def _on_kline(self, event: KlineEvent) -> None:
        """Handle incoming kline event from WS client."""
        self._cache.put_kline(event.symbol, event)
        self._event_bus.publish(event)

    async def _on_depth_update(self, delta: Any) -> None:
        """Handle incoming depth delta from WS client."""
        if self._l2_manager is None:
            return
        binance_symbol = delta.delta.symbol.replace("/", "").upper()
        snapshot = await self._l2_manager.apply_delta(binance_symbol, delta)
        if snapshot is not None:
            self._snapshot_store.update(snapshot.symbol, snapshot)
            self._event_bus.publish(snapshot)

    def _on_l2_snapshot(self, snapshot: OrderBookL2Snapshot) -> None:
        """Handle L2 snapshot callback from BinanceL2Manager."""
        self._snapshot_store.update(snapshot.symbol, snapshot)
        self._event_bus.publish(snapshot)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_running(self) -> None:
        """Raise if service is not running."""
        if not self._running:
            raise MarketDataServiceNotRunning(
                "MarketDataService is not running. Call start() first."
            )
