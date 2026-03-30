"""Tests for pnlclaw_market.service — MarketDataService (multi-source)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from pnlclaw_market.service import MarketDataService, MarketDataServiceError
from pnlclaw_market.source import ExchangeSourceConfig
from pnlclaw_types.market import (
    KlineEvent,
    OrderBookL2Snapshot,
    PriceLevel,
    TickerEvent,
)


class FakeSource:
    """Minimal in-memory ExchangeSource for testing."""

    def __init__(self, exchange: str = "binance", market_type: str = "spot") -> None:
        self._config = ExchangeSourceConfig(exchange=exchange, market_type=market_type)
        self._running = False
        self._symbols: set[str] = set()
        self._tickers: dict[str, TickerEvent] = {}
        self._klines: dict[str, KlineEvent] = {}
        self._books: dict[str, OrderBookL2Snapshot] = {}
        self._ticker_cbs: list[Callable] = []
        self._kline_cbs: list[Callable] = []
        self._book_cbs: list[Callable] = []

    @property
    def config(self) -> ExchangeSourceConfig:
        return self._config

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def subscribe(self, symbol: str, *, ticker: bool = True, kline: bool = True, depth: bool = True) -> None:
        self._symbols.add(symbol)

    async def unsubscribe(self, symbol: str) -> None:
        self._symbols.discard(symbol)

    def get_ticker(self, symbol: str) -> TickerEvent | None:
        return self._tickers.get(symbol)

    def get_kline(self, symbol: str) -> KlineEvent | None:
        return self._klines.get(symbol)

    def get_orderbook(self, symbol: str) -> OrderBookL2Snapshot | None:
        return self._books.get(symbol)

    def get_symbols(self) -> list[str]:
        return sorted(self._symbols)

    def on_ticker(self, callback: Callable[[TickerEvent], Any]) -> None:
        self._ticker_cbs.append(callback)

    def on_kline(self, callback: Callable[[KlineEvent], Any]) -> None:
        self._kline_cbs.append(callback)

    def on_orderbook(self, callback: Callable[[OrderBookL2Snapshot], Any]) -> None:
        self._book_cbs.append(callback)

    def inject_ticker(self, symbol: str, ticker: TickerEvent) -> None:
        self._tickers[symbol] = ticker
        for cb in self._ticker_cbs:
            cb(ticker)

    def inject_kline(self, symbol: str, kline: KlineEvent) -> None:
        self._klines[symbol] = kline
        for cb in self._kline_cbs:
            cb(kline)


def _ticker(exchange: str = "binance", market_type: str = "spot", symbol: str = "BTC/USDT") -> TickerEvent:
    return TickerEvent(
        exchange=exchange,
        market_type=market_type,
        symbol=symbol,
        timestamp=1700000000000,
        last_price=67000.0,
        bid=66999.0,
        ask=67001.0,
        volume_24h=1000.0,
        change_24h_pct=1.5,
    )


class TestMarketDataService:

    def test_is_running_default_false(self) -> None:
        svc = MarketDataService()
        assert svc.is_running is False

    @pytest.mark.asyncio
    async def test_start_and_stop(self) -> None:
        svc = MarketDataService()
        src = FakeSource()
        svc.register_source(src)

        await svc.start()
        assert svc.is_running is True
        assert src.is_running is True

        await svc.stop()
        assert svc.is_running is False
        assert src.is_running is False

    @pytest.mark.asyncio
    async def test_start_idempotent(self) -> None:
        svc = MarketDataService()
        svc.register_source(FakeSource())
        await svc.start()
        await svc.start()
        assert svc.is_running is True
        await svc.stop()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self) -> None:
        svc = MarketDataService()
        await svc.stop()

    def test_get_source_returns_none_when_missing(self) -> None:
        svc = MarketDataService()
        assert svc.get_source("binance", "spot") is None

    def test_register_and_get_source(self) -> None:
        svc = MarketDataService()
        src = FakeSource("okx", "futures")
        svc.register_source(src)
        assert svc.get_source("okx", "futures") is src

    def test_get_ticker_returns_none_when_no_source(self) -> None:
        svc = MarketDataService()
        assert svc.get_ticker("BTC/USDT") is None

    @pytest.mark.asyncio
    async def test_add_symbol_routes_to_source(self) -> None:
        svc = MarketDataService()
        src = FakeSource("binance", "spot")
        svc.register_source(src)
        await svc.start()
        await svc.add_symbol("BTC/USDT", exchange="binance", market_type="spot")
        assert "BTC/USDT" in src.get_symbols()
        await svc.stop()

    @pytest.mark.asyncio
    async def test_add_symbol_unknown_source_raises(self) -> None:
        svc = MarketDataService()
        svc.register_source(FakeSource("binance", "spot"))
        with pytest.raises(MarketDataServiceError):
            await svc.add_symbol("BTC/USDT", exchange="okx", market_type="futures")

    def test_get_symbols_default(self) -> None:
        svc = MarketDataService()
        assert svc.get_symbols() == []

    def test_event_bus_accessible(self) -> None:
        svc = MarketDataService()
        assert svc.event_bus is not None

    def test_on_ticker_callback_bridges_to_event_bus(self) -> None:
        svc = MarketDataService()
        src = FakeSource("binance", "spot")
        svc.register_source(src)

        received: list[TickerEvent] = []
        svc.on_ticker(received.append)

        t = _ticker()
        src.inject_ticker("BTC/USDT", t)
        assert len(received) == 1
        assert received[0] is t

    def test_multiple_sources(self) -> None:
        svc = MarketDataService()
        bs = FakeSource("binance", "spot")
        bf = FakeSource("binance", "futures")
        os_ = FakeSource("okx", "spot")
        of = FakeSource("okx", "futures")

        for s in (bs, bf, os_, of):
            svc.register_source(s)

        assert len(svc.sources) == 4

        t1 = _ticker("binance", "spot")
        bs._tickers["BTC/USDT"] = t1
        assert svc.get_ticker("BTC/USDT", "binance", "spot") is t1
        assert svc.get_ticker("BTC/USDT", "okx", "spot") is None

        t2 = _ticker("okx", "futures")
        of._tickers["BTC/USDT"] = t2
        assert svc.get_ticker("BTC/USDT", "okx", "futures") is t2
