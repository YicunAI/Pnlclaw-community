"""Tests for market data aggregators."""

from __future__ import annotations

import time

import pytest

from pnlclaw_market.aggregators.large_order import LargeOrderDetector
from pnlclaw_market.aggregators.large_trade import LargeTradeDetector
from pnlclaw_market.aggregators.liquidation import LiquidationAggregator
from pnlclaw_types.derivatives import LargeTradeEvent, LiquidationEvent, LiquidationStats
from pnlclaw_types.market import OrderBookL2Snapshot, PriceLevel, TradeEvent


def _make_trade(price: float, quantity: float, side: str = "buy") -> TradeEvent:
    return TradeEvent(
        exchange="binance",
        symbol="BTC/USDT",
        market_type="futures",
        timestamp=int(time.time() * 1000),
        trade_id="1",
        price=price,
        quantity=quantity,
        side=side,
    )


def _make_liquidation(side: str, notional: float) -> LiquidationEvent:
    price = 68000.0
    qty = notional / price
    return LiquidationEvent(
        exchange="binance",
        symbol="BTC/USDT",
        side=side,
        quantity=qty,
        price=price,
        avg_price=price,
        notional_usd=notional,
        timestamp=int(time.time() * 1000),
    )


def _make_orderbook(
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
) -> OrderBookL2Snapshot:
    return OrderBookL2Snapshot(
        exchange="binance",
        symbol="BTC/USDT",
        market_type="futures",
        timestamp=int(time.time() * 1000),
        sequence_id=1,
        bids=[PriceLevel(price=p, quantity=q) for p, q in bids],
        asks=[PriceLevel(price=p, quantity=q) for p, q in asks],
    )


class TestLargeTradeDetector:
    def test_below_threshold_ignored(self) -> None:
        detector = LargeTradeDetector(threshold_usd=100_000)
        trade = _make_trade(68000.0, 1.0)  # 68K < 100K
        result = detector.process(trade)
        assert result is None

    def test_above_threshold_emits(self) -> None:
        detector = LargeTradeDetector(threshold_usd=50_000)
        trade = _make_trade(68000.0, 1.0)  # 68K > 50K
        result = detector.process(trade)
        assert result is not None
        assert isinstance(result, LargeTradeEvent)
        assert result.notional_usd == pytest.approx(68000.0)

    def test_callback_invoked(self) -> None:
        received: list[LargeTradeEvent] = []
        detector = LargeTradeDetector(threshold_usd=10_000)
        detector.on_large_trade(received.append)
        detector.process(_make_trade(68000.0, 0.5))
        assert len(received) == 1
        assert received[0].side == "buy"

    def test_get_recent(self) -> None:
        detector = LargeTradeDetector(threshold_usd=1000)
        for _i in range(10):
            detector.process(_make_trade(68000.0, 0.1))
        assert len(detector.get_recent(5)) == 5
        assert len(detector.get_recent(20)) == 10

    def test_threshold_setter(self) -> None:
        detector = LargeTradeDetector()
        detector.threshold_usd = 200_000
        assert detector.threshold_usd == 200_000


class TestLargeOrderDetector:
    def test_detects_large_bid(self) -> None:
        detector = LargeOrderDetector(threshold_usd=100_000)
        book = _make_orderbook(
            bids=[(68000.0, 2.0), (67999.0, 0.5)],  # 136K, 34K
            asks=[(68001.0, 0.1)],
        )
        events = detector.process(book)
        assert len(events) == 1
        assert events[0].side == "bid"
        assert events[0].event_type == "appeared"
        assert events[0].notional_usd == pytest.approx(136_000.0)

    def test_detects_disappeared(self) -> None:
        detector = LargeOrderDetector(threshold_usd=100_000)
        book1 = _make_orderbook(bids=[(68000.0, 2.0)], asks=[])
        detector.process(book1)

        book2 = _make_orderbook(bids=[(68000.0, 0.1)], asks=[])
        events = detector.process(book2)
        disappeared = [e for e in events if e.event_type == "disappeared"]
        assert len(disappeared) == 1

    def test_get_current_walls(self) -> None:
        detector = LargeOrderDetector(threshold_usd=50_000)
        book = _make_orderbook(
            bids=[(68000.0, 2.0), (67999.0, 0.01)],
            asks=[(68001.0, 3.0), (68002.0, 0.01)],
        )
        walls = detector.get_current_walls(book)
        assert len(walls["bid_walls"]) == 1
        assert len(walls["ask_walls"]) == 1


class TestLiquidationAggregator:
    def test_process_and_get_stats(self) -> None:
        agg = LiquidationAggregator()
        agg.process(_make_liquidation("long", 100_000))
        agg.process(_make_liquidation("short", 50_000))

        stats = agg.get_stats("1h")
        assert stats is not None
        assert isinstance(stats, LiquidationStats)
        assert stats.long_liquidated_usd == pytest.approx(100_000)
        assert stats.short_liquidated_usd == pytest.approx(50_000)
        assert stats.total_liquidated_usd == pytest.approx(150_000)
        assert stats.long_count == 1
        assert stats.short_count == 1

    def test_all_windows_populated(self) -> None:
        agg = LiquidationAggregator()
        agg.process(_make_liquidation("long", 200_000))
        all_stats = agg.get_all_stats()
        assert "15m" in all_stats
        assert "30m" in all_stats
        assert "1h" in all_stats
        assert "4h" in all_stats
        assert "24h" in all_stats

    def test_callbacks_invoked(self) -> None:
        received: list[LiquidationStats] = []
        agg = LiquidationAggregator()
        agg.on_stats_update(received.append)
        agg.process(_make_liquidation("long", 100_000))
        # 5 windows * 1 event = 5 callback invocations
        assert len(received) == 5

    def test_get_recent_events(self) -> None:
        agg = LiquidationAggregator()
        for _ in range(5):
            agg.process(_make_liquidation("long", 10_000))
        events = agg.get_recent_events(3)
        assert len(events) == 3

    def test_largest_single(self) -> None:
        agg = LiquidationAggregator()
        agg.process(_make_liquidation("long", 50_000))
        agg.process(_make_liquidation("short", 200_000))
        agg.process(_make_liquidation("long", 30_000))
        stats = agg.get_stats("1h")
        assert stats is not None
        assert stats.largest_single_usd == pytest.approx(200_000)
