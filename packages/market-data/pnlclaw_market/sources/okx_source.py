"""OKX exchange source — supports both spot and futures (swap).

Wraps ``OKXWSClient`` and ``ReconnectManager`` from ``pnlclaw_exchange``
and exposes the unified ``ExchangeSource`` surface.

OKX uses the same WS endpoints for all instrument types; the difference
is in the ``instId`` suffix: ``BTC-USDT`` for spot vs ``BTC-USDT-SWAP``
for perpetual swaps.  The source transparently appends the suffix.
"""

from __future__ import annotations

import asyncio
import logging
import time as _time
from collections import deque
from collections.abc import Callable
from typing import Any

import httpx

from pnlclaw_exchange import OKXWSClient, ReconnectManager
from pnlclaw_market.cache import MarketDataCache
from pnlclaw_market.event_bus import EventBus
from pnlclaw_market.snapshot_store import SnapshotStore
from pnlclaw_market.source import ExchangeSourceConfig
from pnlclaw_types.derivatives import LiquidationEvent
from pnlclaw_types.market import (
    KlineEvent,
    MarketType,
    OrderBookL2Snapshot,
    TickerEvent,
    TradeEvent,
)

logger = logging.getLogger(__name__)

_OKX_CANDLE_REST_URL = "https://www.okx.com/api/v5/market/candles"
_OKX_HISTORY_CANDLE_REST_URL = "https://www.okx.com/api/v5/market/history-candles"
_MAX_KLINE_BUFFER = 200

_OKX_KLINE_INTERVAL_MAP: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1H",
    "2h": "2H",
    "4h": "4H",
    "1d": "1D",
    "1w": "1W",
}


class OKXSource:
    """OKX data source for one market_type (spot or futures/swap)."""

    def __init__(
        self,
        *,
        market_type: MarketType = "spot",
        proxy_url: str | None = None,
        kline_intervals: list[str] | str = "1h",
        kline_interval: str | None = None,
        cache_ttl: float = 60.0,
        cache_max_size: int = 1000,
    ) -> None:
        self._config = ExchangeSourceConfig(exchange="okx", market_type=market_type)
        self._proxy_url = proxy_url

        # Multi-interval support: accept list or single string (backward compat)
        if kline_interval is not None:
            raw: list[str] | str = kline_interval
        else:
            raw = kline_intervals
        self._kline_intervals: list[str] = [raw] if isinstance(raw, str) else list(raw)
        if not self._kline_intervals:
            self._kline_intervals = ["1h"]
        self._kline_interval = self._kline_intervals[0]  # primary interval for cache compat
        self._okx_kline_intervals: list[str] = [_OKX_KLINE_INTERVAL_MAP.get(i, "1H") for i in self._kline_intervals]
        self._okx_kline_interval = self._okx_kline_intervals[0]
        self._inst_suffix = "-SWAP" if market_type == "futures" else ""
        self._running = False

        self._event_bus = EventBus()
        self._cache = MarketDataCache(ttl_seconds=cache_ttl, max_size=cache_max_size)
        self._snapshot_store = SnapshotStore()

        self._ws_client: OKXWSClient | None = None
        self._reconnect_manager: ReconnectManager | None = None
        self._reconnect_task: asyncio.Task[None] | None = None

        self._subscribed_symbols: set[str] = set()
        self._kline_buffers: dict[str, deque[KlineEvent]] = {}
        self._SNAPSHOT_THROTTLE_S = 0.25
        self._last_snapshot_time: dict[str, float] = {}

        self._http_client = httpx.AsyncClient(
            proxy=self._proxy_url if self._proxy_url else None,
            timeout=15.0,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    # -- helpers --

    def _to_inst_id(self, symbol: str) -> str:
        """Convert unified ``BTC/USDT`` to OKX instId like ``BTC-USDT`` or ``BTC-USDT-SWAP``."""
        base_quote = symbol.replace("/", "-").upper()
        return f"{base_quote}{self._inst_suffix}"

    def _from_inst_id(self, inst_id: str) -> str:
        """Convert OKX instId back to unified symbol."""
        upper = inst_id.upper()
        for suffix in ("-SWAP", "-FUTURES"):
            if upper.endswith(suffix):
                upper = upper[: -len(suffix)]
                break
        return upper.replace("-", "/")

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

        is_futures = self._config.market_type == "futures"
        self._ws_client = OKXWSClient(
            proxy_url=self._proxy_url,
            kline_interval=self._okx_kline_interval,  # default for WS client
            on_ticker=self._on_ticker,
            on_trade=self._on_trade,
            on_kline=self._on_kline,
            on_depth=self._on_depth,
            on_liquidation=self._on_liquidation if is_futures else None,
        )

        self._reconnect_manager = ReconnectManager(self._ws_client)
        self._reconnect_task = asyncio.create_task(
            self._reconnect_manager.run(), name=f"okx-{self._config.market_type}-reconnect"
        )

        if is_futures:
            asyncio.create_task(self._subscribe_futures_global())

        self._running = True
        logger.info("OKXSource started: %s", self._config.market_type)

    async def _subscribe_futures_global(self) -> None:
        """Subscribe to all-market liquidation orders (futures only)."""
        await asyncio.sleep(2.0)
        if self._ws_client is None:
            return
        try:
            await self._ws_client.subscribe_liquidation_orders("SWAP")
            logger.info("OKX futures: subscribed to liquidation-orders")
        except Exception:
            logger.warning("Failed to subscribe to OKX liquidation-orders", exc_info=True)

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

        if self._http_client:
            await self._http_client.aclose()

        self._cache.clear()
        self._snapshot_store.clear()
        self._subscribed_symbols.clear()
        logger.info("OKXSource stopped: %s", self._config.market_type)

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

        inst_id = self._to_inst_id(symbol)
        inst_ids = [inst_id]

        if ticker:
            await self._ws_client.subscribe_ticker(inst_ids)
        if kline:
            for okx_ivl in self._okx_kline_intervals:
                await self._ws_client.subscribe_kline(inst_ids, okx_ivl)
        if depth:
            await self._ws_client.subscribe_depth(inst_ids)
        if trade:
            await self._ws_client.subscribe_trades(inst_ids)

        self._subscribed_symbols.add(symbol)
        logger.info(
            "Subscribed %s on okx/%s (instId=%s, intervals=%s)",
            symbol,
            self._config.market_type,
            inst_id,
            self._kline_intervals,
        )

        if kline:
            for ivl in self._kline_intervals:
                buf_key = f"{symbol}:{ivl}"
                if buf_key not in self._kline_buffers:
                    asyncio.create_task(self._fetch_historical_klines(symbol, ivl))

    async def unsubscribe(self, symbol: str) -> None:
        if not self._ws_client:
            return
        inst_id = self._to_inst_id(symbol)
        streams = [f"tickers:{inst_id}", f"books5:{inst_id}"]
        for okx_ivl in self._okx_kline_intervals:
            streams.append(f"candle{okx_ivl}:{inst_id}")
        try:
            await self._ws_client.unsubscribe(streams)
        except Exception:
            pass
        self._snapshot_store.remove(symbol)
        self._subscribed_symbols.discard(symbol)

    def get_ticker(self, symbol: str) -> TickerEvent | None:
        return self._cache.get_ticker(symbol)

    def get_kline(self, symbol: str) -> KlineEvent | None:
        return self._cache.get_kline(symbol)

    def get_klines(self, symbol: str, limit: int = 100) -> list[KlineEvent]:
        buf = self._kline_buffers.get(f"{symbol}:{self._kline_interval}")
        if buf:
            return list(buf)[-limit:]
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

    # -- REST kline fetch --

    async def _fetch_historical_klines(self, symbol: str, interval: str | None = None) -> None:
        """Fetch historical klines from OKX REST API."""
        ivl = interval or self._kline_interval
        okx_bar = _OKX_KLINE_INTERVAL_MAP.get(ivl, "1H")
        inst_id = self._to_inst_id(symbol)
        params = {"instId": inst_id, "bar": okx_bar, "limit": "200"}
        try:
            resp = await self._http_client.get(_OKX_CANDLE_REST_URL, params=params)
            resp.raise_for_status()
            body = resp.json()

            raw_candles = body.get("data", [])
            buf: deque[KlineEvent] = deque(maxlen=_MAX_KLINE_BUFFER)
            for row in reversed(raw_candles):
                buf.append(
                    KlineEvent(
                        exchange="okx",
                        market_type=self._config.market_type,
                        symbol=symbol,
                        timestamp=int(row[0]),
                        interval=ivl,
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=float(row[5]),
                        closed=row[8] == "1" if len(row) > 8 else True,
                    )
                )
            buf_key = f"{symbol}:{ivl}"
            self._kline_buffers[buf_key] = buf
            logger.info(
                "Fetched %d historical klines (%s) for %s on okx/%s",
                len(buf),
                ivl,
                symbol,
                self._config.market_type,
            )
        except Exception:
            logger.warning(
                "Failed to fetch historical klines (%s) for %s on okx/%s",
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

        OKX ``/market/candles`` only keeps the most recent ~1440 bars.
        When paginating with ``end_time``, we try ``/market/history-candles``
        first (covers years of data, max 100/req), falling back to
        ``/market/candles`` for recent data.
        """
        inst_id = self._to_inst_id(symbol)
        okx_bar = _OKX_KLINE_INTERVAL_MAP.get(interval, "1H")

        try:
            raw_candles: list = []

            if end_time is not None:
                hist_params: dict[str, str] = {
                    "instId": inst_id,
                    "bar": okx_bar,
                    "limit": str(min(limit, 100)),
                    "after": str(end_time),
                }
                resp = await self._http_client.get(_OKX_HISTORY_CANDLE_REST_URL, params=hist_params)
                resp.raise_for_status()
                body = resp.json()
                if body.get("code") == "0":
                    raw_candles = body.get("data", [])

            if not raw_candles:
                params: dict[str, str] = {
                    "instId": inst_id,
                    "bar": okx_bar,
                    "limit": str(min(limit, 300)),
                }
                if end_time is not None:
                    params["after"] = str(end_time)
                resp = await self._http_client.get(_OKX_CANDLE_REST_URL, params=params)
                resp.raise_for_status()
                body = resp.json()
                if body.get("code") == "0":
                    raw_candles = body.get("data", [])

            if not raw_candles:
                return []

            result: list[KlineEvent] = []
            for row in reversed(raw_candles):
                result.append(
                    KlineEvent(
                        exchange="okx",
                        market_type=self._config.market_type,
                        symbol=symbol,
                        timestamp=int(row[0]),
                        interval=interval,
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=float(row[5]),
                        closed=row[8] == "1" if len(row) > 8 else True,
                    )
                )
            return result
        except Exception:
            logger.warning(
                "REST kline fetch failed for %s (%s) on okx/%s",
                symbol,
                interval,
                self._config.market_type,
                exc_info=True,
            )
            return []

    # -- Internal handlers --

    def _stamp(self, event: TickerEvent | KlineEvent | OrderBookL2Snapshot) -> None:
        """Overwrite market_type and normalize the symbol back to BASE/QUOTE."""
        object.__setattr__(event, "market_type", self._config.market_type)
        unified = self._from_inst_id(event.symbol) if "-" in event.symbol else event.symbol
        if unified != event.symbol:
            object.__setattr__(event, "symbol", unified)

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

    def _on_trade(self, event: TradeEvent) -> None:
        self._stamp(event)
        self._event_bus.publish(event)

    def _on_liquidation(self, event: LiquidationEvent) -> None:
        self._stamp(event)
        self._event_bus.publish(event)

    def _on_depth(self, snapshot: OrderBookL2Snapshot) -> None:
        self._stamp(snapshot)
        self._snapshot_store.update(snapshot.symbol, snapshot)

        now = _time.monotonic()
        last = self._last_snapshot_time.get(snapshot.symbol, 0.0)
        if now - last < self._SNAPSHOT_THROTTLE_S:
            return
        self._last_snapshot_time[snapshot.symbol] = now
        self._event_bus.publish(snapshot)
