"""Binance exchange source — supports both spot and USDT-M futures.

Wraps ``BinanceWSClient``, ``BinanceL2Manager``, and ``ReconnectManager``
from ``pnlclaw_exchange`` and exposes the unified ``ExchangeSource`` surface.
"""

from __future__ import annotations

import asyncio
import logging
import time as _time
from collections import deque
from collections.abc import Callable
from typing import Any

import httpx

from pnlclaw_exchange import (
    BinanceL2Manager,
    BinanceNormalizer,
    BinanceWSClient,
    ReconnectManager,
    SymbolNormalizer,
)
from pnlclaw_exchange.exchanges.binance.normalizer import BinanceDepthDelta
from pnlclaw_market.cache import MarketDataCache
from pnlclaw_market.event_bus import EventBus
from pnlclaw_market.snapshot_store import SnapshotStore
from pnlclaw_market.source import ExchangeSourceConfig
from pnlclaw_types.derivatives import FundingRateEvent, LiquidationEvent
from pnlclaw_types.market import (
    KlineEvent,
    MarketType,
    OrderBookL2Snapshot,
    TickerEvent,
    TradeEvent,
)

logger = logging.getLogger(__name__)

_BINANCE_SPOT_WS = "wss://data-stream.binance.vision/ws"
_BINANCE_SPOT_REST = "https://data-api.binance.vision/api/v3/depth"
_BINANCE_SPOT_KLINE_REST = "https://api.binance.com/api/v3/klines"
_BINANCE_FUTURES_WS = "wss://fstream.binance.com/ws"
_BINANCE_FUTURES_REST = "https://fapi.binance.com/fapi/v1/depth"
_BINANCE_FUTURES_KLINE_REST = "https://fapi.binance.com/fapi/v1/klines"

_MAX_KLINE_BUFFER = 200

INTERVAL_MS: dict[str, int] = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
    "3d": 259_200_000,
    "1w": 604_800_000,
}


class BinanceSource:
    """Binance data source for one market_type (spot or futures)."""

    def __init__(
        self,
        *,
        market_type: MarketType = "spot",
        ws_url: str | None = None,
        rest_url: str | None = None,
        proxy_url: str | None = None,
        kline_intervals: list[str] | str = "1h",
        kline_interval: str | None = None,
        cache_ttl: float = 60.0,
        cache_max_size: int = 1000,
    ) -> None:
        is_futures = market_type == "futures"
        self._config = ExchangeSourceConfig(exchange="binance", market_type=market_type)
        self._ws_url = ws_url or (_BINANCE_FUTURES_WS if is_futures else _BINANCE_SPOT_WS)
        self._rest_url = rest_url or (_BINANCE_FUTURES_REST if is_futures else _BINANCE_SPOT_REST)
        self._kline_rest_url = _BINANCE_FUTURES_KLINE_REST if is_futures else _BINANCE_SPOT_KLINE_REST
        self._proxy_url = proxy_url

        # Multi-interval support: accept list or single string (backward compat)
        if kline_interval is not None:
            raw: list[str] | str = kline_interval
        else:
            raw = kline_intervals
        self._kline_intervals: list[str] = [raw] if isinstance(raw, str) else list(raw)
        if not self._kline_intervals:
            self._kline_intervals = ["1h"]
        self._kline_interval = self._kline_intervals[0]  # primary interval for get_kline cache
        self._running = False

        self._event_bus = EventBus()
        self._cache = MarketDataCache(ttl_seconds=cache_ttl, max_size=cache_max_size)
        self._snapshot_store = SnapshotStore()
        self._symbol_normalizer = SymbolNormalizer()
        self._normalizer = BinanceNormalizer(self._symbol_normalizer)

        self._ws_client: BinanceWSClient | None = None
        self._ws_client_futures: BinanceWSClient | None = None
        self._l2_manager: BinanceL2Manager | None = None
        self._reconnect_manager: ReconnectManager | None = None
        self._reconnect_task: asyncio.Task[None] | None = None

        self._subscribed_symbols: set[str] = set()
        self._kline_buffers: dict[str, deque[KlineEvent]] = {}

        self._is_futures = market_type == "futures"
        self._SNAPSHOT_THROTTLE_S = 0.25  # max 4 snapshots/s per symbol
        self._last_snapshot_time: dict[str, float] = {}

    # -- ExchangeSource protocol --

    @property
    def config(self) -> ExchangeSourceConfig:
        return self._config

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if self._running:
            return

        l2_http = httpx.AsyncClient(
            proxy=self._proxy_url if self._proxy_url else None,
            timeout=15.0,
        )
        self._l2_manager = BinanceL2Manager(
            http_client=l2_http,
            symbol_normalizer=self._symbol_normalizer,
            rest_url=self._rest_url,
        )

        self._ws_client = BinanceWSClient(
            url=self._ws_url,
            proxy_url=self._proxy_url,
            symbol_normalizer=self._symbol_normalizer,
            on_ticker=self._on_ticker,
            on_trade=self._on_trade,
            on_kline=self._on_kline,
            on_depth_update=self._on_depth_update,
            on_liquidation=self._on_liquidation if self._is_futures else None,
            on_funding_rate=self._on_funding_rate if self._is_futures else None,
            on_connect=self._on_ws_connect,
        )

        self._reconnect_manager = ReconnectManager(self._ws_client)
        self._reconnect_task = asyncio.create_task(
            self._reconnect_manager.run(), name=f"binance-{self._config.market_type}-reconnect"
        )

        # Futures: subscribe to all-market liquidation and mark price streams
        if self._is_futures:
            asyncio.create_task(self._subscribe_futures_global_streams())

        self._running = True
        logger.info(
            "BinanceSource started: %s (ws=%s)",
            self._config.market_type,
            self._ws_url,
        )

    async def _subscribe_futures_global_streams(self) -> None:
        """Subscribe to all-market liquidation and mark price streams (futures only)."""
        await asyncio.sleep(2.0)  # wait for WS connection
        if self._ws_client is None:
            return
        try:
            await self._ws_client.subscribe_force_order()
            logger.info("Binance futures: subscribed to !forceOrder@arr")
        except Exception:
            logger.warning("Failed to subscribe to forceOrder stream", exc_info=True)
        try:
            await self._ws_client.subscribe_mark_price()
            logger.info("Binance futures: subscribed to !markPrice@arr@1s")
        except Exception:
            logger.warning("Failed to subscribe to markPrice stream", exc_info=True)

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False

        if self._reconnect_manager:
            await self._reconnect_manager.stop()
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        self._reconnect_task = None

        if self._l2_manager:
            await self._l2_manager.close()

        self._cache.clear()
        self._snapshot_store.clear()
        self._subscribed_symbols.clear()
        logger.info("BinanceSource stopped: %s", self._config.market_type)

    async def subscribe(
        self,
        symbol: str,
        *,
        ticker: bool = True,
        kline: bool = True,
        depth: bool = True,
        trade: bool = True,
    ) -> None:
        if not self._running or not self._ws_client:
            return
        binance_syms = [symbol.replace("/", "").lower()]

        if ticker:
            await self._ws_client.subscribe_ticker(binance_syms)
        if kline:
            for ivl in self._kline_intervals:
                await self._ws_client.subscribe_kline(binance_syms, ivl)
        if depth:
            if self._l2_manager:
                binance_upper = symbol.replace("/", "").upper()
                try:
                    await self._l2_manager.initialize(binance_upper)
                except Exception:
                    logger.warning(
                        "L2 init failed for %s on binance/%s", symbol, self._config.market_type, exc_info=True
                    )
            await self._ws_client.subscribe_depth(binance_syms)
        if trade:
            await self._ws_client.subscribe_agg_trade(binance_syms)

        self._subscribed_symbols.add(symbol)
        logger.info(
            "Subscribed %s on binance/%s (intervals=%s)", symbol, self._config.market_type, self._kline_intervals
        )

        if kline:
            for ivl in self._kline_intervals:
                buf_key = f"{symbol}:{ivl}"
                if buf_key not in self._kline_buffers:
                    asyncio.create_task(self._fetch_historical_klines(symbol, ivl))

    async def unsubscribe(self, symbol: str) -> None:
        if not self._ws_client:
            return
        binance_sym = symbol.replace("/", "").lower()
        suffixes = ["@ticker", "@depth@100ms"]
        for ivl in self._kline_intervals:
            suffixes.append(f"@kline_{ivl}")
        for suffix in suffixes:
            try:
                await self._ws_client.unsubscribe([f"{binance_sym}{suffix}"])
            except Exception:
                pass
        self._snapshot_store.remove(symbol)
        self._subscribed_symbols.discard(symbol)

    def get_ticker(self, symbol: str) -> TickerEvent | None:
        return self._cache.get_ticker(symbol)

    def get_kline(self, symbol: str) -> KlineEvent | None:
        return self._cache.get_kline(symbol)

    def get_klines(self, symbol: str, limit: int = 100) -> list[KlineEvent]:
        # Try primary interval first, then merge all intervals for this symbol
        buf = self._kline_buffers.get(f"{symbol}:{self._kline_interval}")
        if buf:
            return list(buf)[-limit:]
        # Fallback: merge all intervals for this symbol
        merged: list[KlineEvent] = []
        for ivl in self._kline_intervals:
            b = self._kline_buffers.get(f"{symbol}:{ivl}")
            if b:
                merged.extend(b)
        if not merged:
            return []
        merged.sort(key=lambda k: k.timestamp)
        return merged[-limit:]

    def get_orderbook(self, symbol: str) -> OrderBookL2Snapshot | None:
        return self._snapshot_store.get_snapshot(symbol)

    def get_symbols(self) -> list[str]:
        return sorted(self._subscribed_symbols)

    def on_ticker(self, callback: Callable[[TickerEvent], Any]) -> None:
        self._event_bus.subscribe(TickerEvent, callback)

    def on_kline(self, callback: Callable[[KlineEvent], Any]) -> None:
        self._event_bus.subscribe(KlineEvent, callback)

    def on_orderbook(self, callback: Callable[[OrderBookL2Snapshot], Any]) -> None:
        self._event_bus.subscribe(OrderBookL2Snapshot, callback)

    def on_trade(self, callback: Callable[[TradeEvent], Any]) -> None:
        self._event_bus.subscribe(TradeEvent, callback)

    def on_liquidation(self, callback: Callable[[LiquidationEvent], Any]) -> None:
        self._event_bus.subscribe(LiquidationEvent, callback)

    def on_funding_rate(self, callback: Callable[[FundingRateEvent], Any]) -> None:
        self._event_bus.subscribe(FundingRateEvent, callback)

    # -- REST kline fetch --

    async def _fetch_historical_klines(self, symbol: str, interval: str | None = None) -> None:
        """Fetch historical klines from Binance REST API and populate the buffer."""
        ivl = interval or self._kline_interval
        binance_sym = symbol.replace("/", "").upper()
        params = {"symbol": binance_sym, "interval": ivl, "limit": 200}
        try:
            proxy = self._proxy_url if self._proxy_url else None
            async with httpx.AsyncClient(proxy=proxy, timeout=15.0) as client:
                resp = await client.get(self._kline_rest_url, params=params)
                resp.raise_for_status()
                raw = resp.json()

            buf: deque[KlineEvent] = deque(maxlen=_MAX_KLINE_BUFFER)
            for row in raw:
                buf.append(
                    KlineEvent(
                        exchange="binance",
                        market_type=self._config.market_type,
                        symbol=symbol,
                        timestamp=int(row[0]),
                        interval=ivl,
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=float(row[5]),
                        closed=True,
                    )
                )
            buf_key = f"{symbol}:{ivl}"
            self._kline_buffers[buf_key] = buf
            logger.info(
                "Fetched %d historical klines (%s) for %s on binance/%s",
                len(buf),
                ivl,
                symbol,
                self._config.market_type,
            )
        except Exception:
            logger.warning(
                "Failed to fetch historical klines (%s) for %s on binance/%s",
                ivl,
                symbol,
                self._config.market_type,
                exc_info=True,
            )

    async def fetch_klines_rest(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 200,
        end_time: int | None = None,
    ) -> list[KlineEvent]:
        """On-demand REST fetch of klines for any interval.

        Args:
            end_time: If provided, fetch candles *before* this timestamp (ms).
                      Enables historical pagination (infinite scroll).
        """
        binance_sym = symbol.replace("/", "").upper()
        params: dict[str, str | int] = {"symbol": binance_sym, "interval": interval, "limit": limit}
        if end_time is not None:
            params["endTime"] = end_time
        try:
            proxy = self._proxy_url if self._proxy_url else None
            async with httpx.AsyncClient(proxy=proxy, timeout=15.0) as client:
                resp = await client.get(self._kline_rest_url, params=params)
                resp.raise_for_status()
                raw = resp.json()
            result: list[KlineEvent] = []
            now_ms = int(_time.time() * 1000)
            for row in raw:
                open_time = int(row[0])
                interval_ms = INTERVAL_MS.get(interval, 3_600_000)
                candle_end = open_time + interval_ms
                is_closed = now_ms >= candle_end
                result.append(
                    KlineEvent(
                        exchange="binance",
                        market_type=self._config.market_type,
                        symbol=symbol,
                        timestamp=open_time,
                        interval=interval,
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=float(row[5]),
                        closed=is_closed,
                    )
                )
            logger.info(
                "REST fetched %d klines (%s) for %s on binance/%s",
                len(result),
                interval,
                symbol,
                self._config.market_type,
            )
            return result
        except Exception:
            logger.warning(
                "REST kline fetch failed for %s (%s) on binance/%s",
                symbol,
                interval,
                self._config.market_type,
                exc_info=True,
            )
            return []

    # -- Reconnect handler --

    async def _on_ws_connect(self) -> None:
        """Handle WebSocket (re)connection by re-initializing L2 orderbooks.

        On first connection ``_subscribed_symbols`` is empty, so this is a no-op.
        On reconnect it fetches fresh REST snapshots for every subscribed symbol
        so that the local books don't carry stale state that would trigger false
        gap detections in the diff depth stream.
        """
        if not self._l2_manager or not self._subscribed_symbols:
            return
        await self._l2_manager.reinitialize_all()

    # -- Internal handlers --

    def _stamp(self, event: TickerEvent | KlineEvent | OrderBookL2Snapshot) -> None:
        """Set market_type on outgoing events."""
        object.__setattr__(event, "market_type", self._config.market_type)

    def _on_ticker(self, event: TickerEvent) -> None:
        self._stamp(event)
        self._cache.put_ticker(event.symbol, event)
        self._event_bus.publish(event)

    def _on_kline(self, event: KlineEvent) -> None:
        self._stamp(event)
        self._cache.put_kline(event.symbol, event)

        buf_key = f"{event.symbol}:{event.interval}" if event.interval else event.symbol
        buf = self._kline_buffers.get(buf_key)
        if buf is not None:
            if buf and buf[-1].timestamp == event.timestamp:
                buf[-1] = event
            else:
                buf.append(event)

        self._event_bus.publish(event)

    async def _on_depth_update(self, delta: BinanceDepthDelta) -> None:
        if not self._l2_manager:
            return
        binance_symbol = delta.delta.symbol.replace("/", "").upper()
        applied = await self._l2_manager.apply_delta(binance_symbol, delta)
        if not applied:
            return

        now = _time.monotonic()
        sym = delta.delta.symbol
        last = self._last_snapshot_time.get(sym, 0.0)
        if now - last < self._SNAPSHOT_THROTTLE_S:
            return

        self._last_snapshot_time[sym] = now
        snapshot = self._l2_manager.get_snapshot(binance_symbol)
        if snapshot:
            self._stamp(snapshot)
            self._snapshot_store.update(snapshot.symbol, snapshot)
            self._event_bus.publish(snapshot)

    def _on_trade(self, event: TradeEvent) -> None:
        self._stamp(event)
        self._event_bus.publish(event)

    def _on_liquidation(self, event: LiquidationEvent) -> None:
        self._stamp(event)
        self._event_bus.publish(event)

    def _on_funding_rate(self, event: FundingRateEvent) -> None:
        self._stamp(event)
        self._event_bus.publish(event)
