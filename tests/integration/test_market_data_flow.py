"""Integration test: market data flow from exchange WS to cache/events.

Tests the full pipeline:
  BinanceWSClient callbacks → MarketDataService → Cache + EventBus
  without requiring a real exchange connection.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pnlclaw_exchange.exchanges.binance.normalizer import BinanceDepthDelta, BinanceNormalizer
from pnlclaw_exchange.normalizers.symbol import SymbolNormalizer
from pnlclaw_market.service import MarketDataService
from pnlclaw_types.market import KlineEvent, OrderBookL2Delta, TickerEvent


@pytest.fixture
def symbol_normalizer() -> SymbolNormalizer:
    return SymbolNormalizer()


@pytest.fixture
def normalizer(symbol_normalizer: SymbolNormalizer) -> BinanceNormalizer:
    return BinanceNormalizer(symbol_normalizer)


def _make_ticker_event() -> TickerEvent:
    return TickerEvent(
        exchange="binance",
        symbol="BTC/USDT",
        timestamp=1700000000000,
        last_price=42000.0,
        bid=41999.0,
        ask=42001.0,
        volume_24h=1500.0,
        change_24h_pct=1.2,
    )


def _make_kline_event() -> KlineEvent:
    return KlineEvent(
        exchange="binance",
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


class TestMarketDataServiceCallbacks:
    """Test that callbacks properly populate cache and event bus."""

    def test_ticker_callback_populates_cache(self) -> None:
        svc = MarketDataService.__new__(MarketDataService)
        svc._running = True
        from pnlclaw_market.cache import MarketDataCache
        from pnlclaw_market.event_bus import EventBus

        svc._cache = MarketDataCache()
        svc._event_bus = EventBus()
        svc._snapshot_store = MagicMock()
        svc._stream_manager = MagicMock()
        svc._stream_manager.active_symbols.return_value = ["BTC/USDT"]

        ticker = _make_ticker_event()
        svc._on_ticker(ticker)

        cached = svc.get_ticker("BTC/USDT")
        assert cached is not None
        assert cached.last_price == 42000.0
        assert cached.symbol == "BTC/USDT"

    def test_kline_callback_populates_cache(self) -> None:
        svc = MarketDataService.__new__(MarketDataService)
        svc._running = True
        from pnlclaw_market.cache import MarketDataCache
        from pnlclaw_market.event_bus import EventBus

        svc._cache = MarketDataCache()
        svc._event_bus = EventBus()
        svc._snapshot_store = MagicMock()
        svc._stream_manager = MagicMock()

        kline = _make_kline_event()
        svc._on_kline(kline)

        cached = svc.get_kline("BTC/USDT")
        assert cached is not None
        assert cached.close == 42000.0

    def test_event_bus_receives_ticker(self) -> None:
        svc = MarketDataService.__new__(MarketDataService)
        svc._running = True
        from pnlclaw_market.cache import MarketDataCache
        from pnlclaw_market.event_bus import EventBus

        svc._cache = MarketDataCache()
        svc._event_bus = EventBus()
        svc._snapshot_store = MagicMock()

        received: list[TickerEvent] = []
        svc._event_bus.subscribe(TickerEvent, received.append)

        ticker = _make_ticker_event()
        svc._on_ticker(ticker)

        assert len(received) == 1
        assert received[0].last_price == 42000.0


class TestBinanceNormalization:
    """Test raw Binance JSON → typed events."""

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


class TestEndToEndDataFlow:
    """Test data flowing through the full pipeline with mocks."""

    @pytest.mark.asyncio
    async def test_add_symbol_subscribes_streams(self) -> None:
        """add_symbol should drive StreamManager subscriptions."""
        svc = MarketDataService.__new__(MarketDataService)
        svc._running = True
        from pnlclaw_market.cache import MarketDataCache
        from pnlclaw_market.event_bus import EventBus
        from pnlclaw_market.snapshot_store import SnapshotStore

        svc._cache = MarketDataCache()
        svc._event_bus = EventBus()
        svc._snapshot_store = SnapshotStore()
        svc._stream_manager = MagicMock()
        svc._stream_manager.start_stream = AsyncMock()
        svc._l2_manager = MagicMock()
        svc._l2_manager.initialize = AsyncMock()

        await svc.add_symbol("BTC/USDT")

        assert svc._stream_manager.start_stream.call_count == 3
        svc._l2_manager.initialize.assert_awaited_once_with("BTCUSDT")

    @pytest.mark.asyncio
    async def test_ticker_to_event_bus_flow(self) -> None:
        """Ticker callback → cache + event bus delivery."""
        svc = MarketDataService.__new__(MarketDataService)
        svc._running = True
        from pnlclaw_market.cache import MarketDataCache
        from pnlclaw_market.event_bus import EventBus

        svc._cache = MarketDataCache()
        svc._event_bus = EventBus()
        svc._snapshot_store = MagicMock()
        svc._stream_manager = MagicMock()

        events: list[TickerEvent] = []
        svc.on_ticker(events.append)

        ticker = _make_ticker_event()
        svc._on_ticker(ticker)

        assert len(events) == 1
        assert events[0].last_price == 42000.0
        assert svc.get_ticker("BTC/USDT") is not None
