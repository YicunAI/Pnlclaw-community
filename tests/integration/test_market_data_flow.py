"""Integration test: market data flow from exchange WS to cache/events.

Tests the full pipeline:
  ExchangeSource callbacks → MarketDataService EventBus → consumers
  without requiring a real exchange connection.

Also tests Binance normalization directly.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from pnlclaw_exchange.exchanges.binance.normalizer import BinanceDepthDelta, BinanceNormalizer
from pnlclaw_exchange.normalizers.symbol import SymbolNormalizer
from pnlclaw_market.service import MarketDataService
from pnlclaw_market.source import ExchangeSourceConfig
from pnlclaw_types.market import KlineEvent, OrderBookL2Snapshot, PriceLevel, TickerEvent


@pytest.fixture
def symbol_normalizer() -> SymbolNormalizer:
    return SymbolNormalizer()


@pytest.fixture
def normalizer(symbol_normalizer: SymbolNormalizer) -> BinanceNormalizer:
    return BinanceNormalizer(symbol_normalizer)


def _make_ticker_event(exchange: str = "binance", market_type: str = "spot") -> TickerEvent:
    return TickerEvent(
        exchange=exchange,
        market_type=market_type,
        symbol="BTC/USDT",
        timestamp=1700000000000,
        last_price=42000.0,
        bid=41999.0,
        ask=42001.0,
        volume_24h=1500.0,
        change_24h_pct=1.2,
    )


def _make_kline_event(exchange: str = "binance", market_type: str = "spot") -> KlineEvent:
    return KlineEvent(
        exchange=exchange,
        market_type=market_type,
        symbol="BTC/USDT",
        timestamp=1700000000000,
        interval="1h",
        open=41500.0,
        high=42500.0,
        low=41000.0,
        close=42000.0,
        volume=100.0,
        closed=True,
    )


class FakeSource:
    """In-memory ExchangeSource for integration testing."""

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

    def inject_ticker(self, symbol: str, event: TickerEvent) -> None:
        self._tickers[symbol] = event
        for cb in self._ticker_cbs:
            cb(event)

    def inject_kline(self, symbol: str, event: KlineEvent) -> None:
        self._klines[symbol] = event
        for cb in self._kline_cbs:
            cb(event)


class TestMultiSourceEventFlow:
    """Test that events from individual sources bridge to the unified EventBus."""

    def test_ticker_from_source_reaches_service_event_bus(self) -> None:
        svc = MarketDataService()
        src = FakeSource("binance", "spot")
        svc.register_source(src)

        received: list[TickerEvent] = []
        svc.on_ticker(received.append)

        ticker = _make_ticker_event()
        src.inject_ticker("BTC/USDT", ticker)

        assert len(received) == 1
        assert received[0].last_price == 42000.0
        assert received[0].exchange == "binance"

    def test_kline_from_source_reaches_service_event_bus(self) -> None:
        svc = MarketDataService()
        src = FakeSource("okx", "futures")
        svc.register_source(src)

        received: list[KlineEvent] = []
        svc.on_kline(received.append)

        kline = _make_kline_event("okx", "futures")
        src.inject_kline("BTC/USDT", kline)

        assert len(received) == 1
        assert received[0].close == 42000.0
        assert received[0].exchange == "okx"

    def test_events_from_multiple_sources_arrive_on_same_bus(self) -> None:
        svc = MarketDataService()
        bs = FakeSource("binance", "spot")
        of = FakeSource("okx", "futures")
        svc.register_source(bs)
        svc.register_source(of)

        received: list[TickerEvent] = []
        svc.on_ticker(received.append)

        bs.inject_ticker("BTC/USDT", _make_ticker_event("binance", "spot"))
        of.inject_ticker("BTC/USDT", _make_ticker_event("okx", "futures"))

        assert len(received) == 2
        exchanges = {r.exchange for r in received}
        assert exchanges == {"binance", "okx"}

    @pytest.mark.asyncio
    async def test_add_symbol_routes_to_correct_source(self) -> None:
        svc = MarketDataService()
        bs = FakeSource("binance", "spot")
        of = FakeSource("okx", "futures")
        svc.register_source(bs)
        svc.register_source(of)
        await svc.start()

        await svc.add_symbol("ETH/USDT", exchange="okx", market_type="futures")

        assert "ETH/USDT" in of.get_symbols()
        assert "ETH/USDT" not in bs.get_symbols()
        await svc.stop()


class TestBinanceNormalization:
    """Test raw Binance JSON -> typed events."""

    def test_normalize_ticker(self, normalizer: BinanceNormalizer) -> None:
        raw = {
            "e": "24hrTicker",
            "s": "BTCUSDT",
            "c": "42000.00",
            "b": "41999.50",
            "a": "42000.50",
            "v": "1500.0",
            "P": "1.2",
            "E": 1700000000000,
        }
        event = normalizer.normalize(raw)
        assert isinstance(event, TickerEvent)
        assert event.symbol == "BTC/USDT"
        assert event.last_price == 42000.0

    def test_normalize_kline(self, normalizer: BinanceNormalizer) -> None:
        raw = {
            "e": "kline",
            "s": "ETHUSDT",
            "E": 1700000000000,
            "k": {
                "t": 1700000000000,
                "s": "ETHUSDT",
                "i": "1h",
                "o": "2200.00",
                "h": "2250.00",
                "l": "2180.00",
                "c": "2240.00",
                "v": "500.0",
                "x": True,
            },
        }
        event = normalizer.normalize(raw)
        assert isinstance(event, KlineEvent)
        assert event.symbol == "ETH/USDT"
        assert event.close == 2240.0
        assert event.closed is True

    def test_normalize_depth(self, normalizer: BinanceNormalizer) -> None:
        raw = {
            "e": "depthUpdate",
            "s": "BTCUSDT",
            "E": 1700000000000,
            "U": 100,
            "u": 101,
            "b": [["42000.00", "1.5"]],
            "a": [["42001.00", "0.5"]],
        }
        event = normalizer.normalize(raw)
        assert isinstance(event, BinanceDepthDelta)
        assert event.first_update_id == 100
        assert event.last_update_id == 101
        assert len(event.delta.bids) == 1
        assert len(event.delta.asks) == 1
