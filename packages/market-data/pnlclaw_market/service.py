"""Market data main service: multi-source manager for exchange data.

Manages multiple ``ExchangeSource`` instances (one per exchange/market_type
combination) and provides a unified query and event bus interface.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from pnlclaw_market.aggregators.large_order import LargeOrderDetector
from pnlclaw_market.aggregators.large_trade import LargeTradeDetector
from pnlclaw_market.aggregators.liquidation import LiquidationAggregator
from pnlclaw_market.event_bus import EventBus
from pnlclaw_market.source import ExchangeSource
from pnlclaw_types.derivatives import (
    FundingRateEvent,
    LargeOrderEvent,
    LargeTradeEvent,
    LiquidationEvent,
    LiquidationStats,
    OpenInterestSnapshot,
)
from pnlclaw_types.market import (
    KlineEvent,
    OrderBookL2Snapshot,
    TickerEvent,
    TradeEvent,
)

logger = logging.getLogger(__name__)

SourceKey = tuple[str, str]  # (exchange, market_type)


class MarketDataServiceError(Exception):
    """Base exception for MarketDataService errors."""


class MarketDataServiceNotRunning(MarketDataServiceError):
    """Raised when querying a service that has not been started."""


class MarketDataService:
    """Central multi-source market data service.

    Each source is an ``ExchangeSource`` keyed by ``(exchange, market_type)``.
    The service delegates all data operations to the appropriate source and
    aggregates events onto a single ``EventBus``.

    Backward-compatible: methods without explicit ``exchange``/``market_type``
    default to ``("binance", "spot")``.
    """

    def __init__(
        self,
        *,
        large_trade_threshold_usd: float = 50_000.0,
        large_order_threshold_usd: float = 100_000.0,
    ) -> None:
        self._sources: dict[SourceKey, ExchangeSource] = {}
        self._event_bus = EventBus()
        self._running = False

        # --- Tactical dashboard aggregators ---
        self._large_trade_detector = LargeTradeDetector(threshold_usd=large_trade_threshold_usd)
        self._large_order_detector = LargeOrderDetector(threshold_usd=large_order_threshold_usd)
        self._liquidation_aggregator = LiquidationAggregator()
        self._funding_rate_store: dict[str, FundingRateEvent] = {}
        self._open_interest_store: dict[str, OpenInterestSnapshot] = {}

        # --- Kline batch cache (key → klines, avoids re-fetching) ---
        self._kline_cache: dict[str, list[KlineEvent]] = {}
        self._kline_cache_max = 20

    # ------------------------------------------------------------------
    # Source registration
    # ------------------------------------------------------------------

    def register_source(self, source: ExchangeSource) -> None:
        """Register an exchange source.

        Must be called **before** :meth:`start`.  If a source with the
        same key already exists it is replaced (the old one is not stopped).
        """
        key: SourceKey = (source.config.exchange, source.config.market_type)
        self._sources[key] = source

        # Bridge per-source events into the unified EventBus
        source.on_ticker(lambda e: self._event_bus.publish(e))
        source.on_kline(lambda e: self._event_bus.publish(e))
        source.on_orderbook(lambda e: self._event_bus.publish(e))

        # Bridge trade events → large trade detector
        if hasattr(source, "on_trade"):
            source.on_trade(self._on_trade_event)  # type: ignore[attr-defined]

        # Bridge orderbook → large order detector
        source.on_orderbook(self._on_orderbook_for_detection)

        # Bridge derivatives events if source supports them
        if hasattr(source, "on_liquidation"):
            source.on_liquidation(self._on_liquidation_event)  # type: ignore[attr-defined]
        if hasattr(source, "on_funding_rate"):
            source.on_funding_rate(self._on_funding_rate_event)  # type: ignore[attr-defined]

        logger.info("Registered source: %s/%s", *key)

    def get_source(
        self, exchange: str = "binance", market_type: str = "spot"
    ) -> ExchangeSource | None:
        """Return the source for *exchange*/*market_type*, or None."""
        return self._sources.get((exchange, market_type))

    @property
    def sources(self) -> dict[SourceKey, ExchangeSource]:
        return dict(self._sources)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start all registered sources."""
        if self._running:
            return

        for key, source in self._sources.items():
            try:
                await source.start()
                logger.info("Source started: %s/%s", *key)
            except Exception:
                logger.error("Failed to start source %s/%s", *key, exc_info=True)

        self._running = True
        logger.info(
            "MarketDataService started with %d source(s)", len(self._sources)
        )

    async def stop(self) -> None:
        """Stop all sources."""
        if not self._running:
            return
        self._running = False

        for key, source in self._sources.items():
            try:
                await source.stop()
            except Exception:
                logger.error("Error stopping source %s/%s", *key, exc_info=True)

        logger.info("MarketDataService stopped")

    # ------------------------------------------------------------------
    # Symbol management
    # ------------------------------------------------------------------

    async def add_symbol(
        self,
        symbol: str,
        *,
        exchange: str = "binance",
        market_type: str = "spot",
        ticker: bool = True,
        kline: bool = True,
        depth: bool = True,
    ) -> None:
        """Subscribe to streams on a specific source."""
        source = self._require_source(exchange, market_type)
        await source.subscribe(symbol, ticker=ticker, kline=kline, depth=depth)

    async def remove_symbol(
        self,
        symbol: str,
        *,
        exchange: str = "binance",
        market_type: str = "spot",
    ) -> None:
        """Unsubscribe from a specific source."""
        source = self._require_source(exchange, market_type)
        await source.unsubscribe(symbol)

    # ------------------------------------------------------------------
    # Data access (source-routed)
    # ------------------------------------------------------------------

    def get_ticker(
        self,
        symbol: str,
        exchange: str = "binance",
        market_type: str = "spot",
    ) -> TickerEvent | None:
        source = self._sources.get((exchange, market_type))
        return source.get_ticker(symbol) if source else None

    def get_kline(
        self,
        symbol: str,
        exchange: str = "binance",
        market_type: str = "spot",
    ) -> KlineEvent | None:
        source = self._sources.get((exchange, market_type))
        return source.get_kline(symbol) if source else None

    def get_klines(
        self,
        symbol: str,
        exchange: str = "binance",
        market_type: str = "spot",
        limit: int = 100,
    ) -> list[KlineEvent]:
        source = self._sources.get((exchange, market_type))
        if source and hasattr(source, "get_klines"):
            return source.get_klines(symbol, limit)
        return []

    async def fetch_klines_rest(
        self,
        symbol: str,
        exchange: str = "binance",
        market_type: str = "spot",
        interval: str = "1h",
        limit: int = 200,
        end_time: int | None = None,
    ) -> list[KlineEvent]:
        """On-demand REST fetch for any interval (bypasses WS buffer).

        Args:
            end_time: If provided, fetch candles *before* this timestamp (ms).
                      Enables historical pagination (infinite scroll).
        """
        source = self._sources.get((exchange, market_type))
        if source and hasattr(source, "fetch_klines_rest"):
            return await source.fetch_klines_rest(symbol, interval, limit, end_time=end_time)
        return []

    async def fetch_klines_batch(
        self,
        symbol: str,
        exchange: str = "binance",
        market_type: str = "spot",
        interval: str = "1h",
        total: int = 1000,
    ) -> list[KlineEvent]:
        """Paginated batch fetch: pull *total* klines by walking backwards.

        Automatically paginates using ``end_time`` from the oldest kline
        in each batch until the desired count is reached or no more data
        is returned.  Results are cached to avoid redundant REST calls.

        Args:
            total: Target number of klines to fetch.

        Returns:
            List of KlineEvent sorted oldest→newest, up to *total* items.
        """
        cache_key = f"{exchange}:{market_type}:{symbol}:{interval}:{total}"
        cached = self._kline_cache.get(cache_key)
        if cached is not None and len(cached) >= total:
            logger.info("Kline cache hit: %s (%d candles)", cache_key, len(cached))
            return cached[:total]

        source = self._sources.get((exchange, market_type))
        if source is None or not hasattr(source, "fetch_klines_rest"):
            return []

        page_size = 200
        if "binance" in exchange:
            page_size = 1000
        elif "okx" in exchange:
            page_size = 100

        all_klines: list[KlineEvent] = []
        cursor: int | None = None
        pages = 0
        empty_streak = 0

        while len(all_klines) < total:
            batch_limit = min(page_size, total - len(all_klines))
            batch = await source.fetch_klines_rest(
                symbol, interval, batch_limit, end_time=cursor,
            )
            if not batch:
                empty_streak += 1
                if empty_streak >= 2:
                    break
                continue

            empty_streak = 0
            all_klines = batch + all_klines
            pages += 1
            oldest_ts = getattr(batch[0], "timestamp", None)
            if oldest_ts is None or oldest_ts <= 0:
                break
            cursor = oldest_ts - 1

            if len(batch) < max(batch_limit // 2, 1):
                break

        seen: set[int] = set()
        deduped: list[KlineEvent] = []
        for k in all_klines:
            ts = getattr(k, "timestamp", 0)
            if ts not in seen:
                seen.add(ts)
                deduped.append(k)

        deduped.sort(key=lambda k: getattr(k, "timestamp", 0))
        result = deduped[:total]

        if len(self._kline_cache) >= self._kline_cache_max:
            oldest_key = next(iter(self._kline_cache))
            del self._kline_cache[oldest_key]
        self._kline_cache[cache_key] = result
        logger.info(
            "Kline batch fetched: %s → %d candles in %d pages (cached)",
            cache_key, len(result), pages,
        )

        return result

    def get_orderbook(
        self,
        symbol: str,
        exchange: str = "binance",
        market_type: str = "spot",
    ) -> OrderBookL2Snapshot | None:
        source = self._sources.get((exchange, market_type))
        return source.get_orderbook(symbol) if source else None

    def get_symbols(
        self,
        exchange: str = "binance",
        market_type: str = "spot",
    ) -> list[str]:
        source = self._sources.get((exchange, market_type))
        return source.get_symbols() if source else []

    # ------------------------------------------------------------------
    # Unified event subscription
    # ------------------------------------------------------------------

    def on_ticker(self, callback: Callable[[TickerEvent], Any]) -> None:
        self._event_bus.subscribe(TickerEvent, callback)

    def on_kline(self, callback: Callable[[KlineEvent], Any]) -> None:
        self._event_bus.subscribe(KlineEvent, callback)

    def on_orderbook(self, callback: Callable[[OrderBookL2Snapshot], Any]) -> None:
        self._event_bus.subscribe(OrderBookL2Snapshot, callback)

    # ------------------------------------------------------------------
    # Derivatives event subscriptions
    # ------------------------------------------------------------------

    def on_trade(self, callback: Callable[[TradeEvent], Any]) -> None:
        self._event_bus.subscribe(TradeEvent, callback)

    def on_large_trade(self, callback: Callable[[LargeTradeEvent], Any]) -> None:
        self._event_bus.subscribe(LargeTradeEvent, callback)

    def on_large_order(self, callback: Callable[[LargeOrderEvent], Any]) -> None:
        self._event_bus.subscribe(LargeOrderEvent, callback)

    def on_liquidation(self, callback: Callable[[LiquidationEvent], Any]) -> None:
        self._event_bus.subscribe(LiquidationEvent, callback)

    def on_liquidation_stats(self, callback: Callable[[LiquidationStats], Any]) -> None:
        self._event_bus.subscribe(LiquidationStats, callback)

    def on_funding_rate(self, callback: Callable[[FundingRateEvent], Any]) -> None:
        self._event_bus.subscribe(FundingRateEvent, callback)

    # ------------------------------------------------------------------
    # Internal aggregation handlers
    # ------------------------------------------------------------------

    def _on_trade_event(self, trade: TradeEvent) -> None:
        """Process a trade through the large-trade detector and publish."""
        self._event_bus.publish(trade)
        large = self._large_trade_detector.process(trade)
        if large:
            self._event_bus.publish(large)

    def _on_orderbook_for_detection(self, snapshot: OrderBookL2Snapshot) -> None:
        """Run large-order detection on each orderbook snapshot."""
        events = self._large_order_detector.process(snapshot)
        for ev in events:
            self._event_bus.publish(ev)

    def _on_liquidation_event(self, event: LiquidationEvent) -> None:
        """Process a liquidation event and publish stats."""
        self._event_bus.publish(event)
        self._liquidation_aggregator.process(event)
        for stats in self._liquidation_aggregator.get_all_stats().values():
            self._event_bus.publish(stats)

    def _on_funding_rate_event(self, event: FundingRateEvent) -> None:
        """Cache funding rate event and publish."""
        key = f"{event.exchange}:{event.symbol}"
        self._funding_rate_store[key] = event
        self._event_bus.publish(event)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_source(self, exchange: str, market_type: str) -> ExchangeSource:
        source = self._sources.get((exchange, market_type))
        if source is None:
            raise MarketDataServiceError(
                f"No source registered for {exchange}/{market_type}"
            )
        return source
