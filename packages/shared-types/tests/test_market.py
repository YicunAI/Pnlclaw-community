"""Tests for pnlclaw_types.market — serialization/deserialization roundtrips."""

from pnlclaw_types.market import (
    KlineEvent,
    OrderBookL2Delta,
    OrderBookL2Snapshot,
    PriceLevel,
    TickerEvent,
    TradeEvent,
)


class TestPriceLevel:
    def test_roundtrip(self):
        pl = PriceLevel(price=67000.0, quantity=1.5)
        raw = pl.model_dump_json()
        restored = PriceLevel.model_validate_json(raw)
        assert restored == pl


class TestTickerEvent:
    def test_roundtrip(self):
        t = TickerEvent(
            exchange="binance",
            symbol="BTC/USDT",
            timestamp=1711000000000,
            last_price=67000.0,
            bid=66999.5,
            ask=67000.5,
            volume_24h=12345.67,
            change_24h_pct=2.35,
        )
        raw = t.model_dump_json()
        restored = TickerEvent.model_validate_json(raw)
        assert restored == t

    def test_standard_fields(self):
        """All market events must have exchange, symbol, timestamp."""
        fields = set(TickerEvent.model_fields.keys())
        assert {"exchange", "symbol", "timestamp"}.issubset(fields)


class TestTradeEvent:
    def test_roundtrip(self):
        t = TradeEvent(
            exchange="binance",
            symbol="ETH/USDT",
            timestamp=1711000000000,
            trade_id="987654",
            price=3500.0,
            quantity=10.0,
            side="buy",
        )
        raw = t.model_dump_json()
        restored = TradeEvent.model_validate_json(raw)
        assert restored == t

    def test_standard_fields(self):
        fields = set(TradeEvent.model_fields.keys())
        assert {"exchange", "symbol", "timestamp"}.issubset(fields)


class TestKlineEvent:
    def test_roundtrip(self):
        k = KlineEvent(
            exchange="binance",
            symbol="BTC/USDT",
            timestamp=1711000000000,
            interval="1h",
            open=66800.0,
            high=67200.0,
            low=66700.0,
            close=67000.0,
            volume=1234.56,
            closed=True,
        )
        raw = k.model_dump_json()
        restored = KlineEvent.model_validate_json(raw)
        assert restored == k

    def test_standard_fields(self):
        fields = set(KlineEvent.model_fields.keys())
        assert {"exchange", "symbol", "timestamp"}.issubset(fields)


class TestOrderBookL2Snapshot:
    def test_roundtrip(self):
        ob = OrderBookL2Snapshot(
            exchange="binance",
            symbol="BTC/USDT",
            timestamp=1711000000000,
            sequence_id=100001,
            bids=[PriceLevel(price=66999.0, quantity=2.0)],
            asks=[PriceLevel(price=67001.0, quantity=1.0)],
        )
        raw = ob.model_dump_json()
        restored = OrderBookL2Snapshot.model_validate_json(raw)
        assert restored == ob
        assert len(restored.bids) == 1
        assert len(restored.asks) == 1

    def test_standard_fields(self):
        fields = set(OrderBookL2Snapshot.model_fields.keys())
        assert {"exchange", "symbol", "timestamp"}.issubset(fields)

    def test_empty_book(self):
        ob = OrderBookL2Snapshot(
            exchange="binance",
            symbol="BTC/USDT",
            timestamp=1711000000000,
            sequence_id=1,
        )
        assert ob.bids == []
        assert ob.asks == []


class TestOrderBookL2Delta:
    def test_roundtrip(self):
        delta = OrderBookL2Delta(
            exchange="binance",
            symbol="BTC/USDT",
            timestamp=1711000000001,
            sequence_id=100002,
            bids=[PriceLevel(price=66999.0, quantity=2.5)],
            asks=[PriceLevel(price=67001.0, quantity=0.0)],
        )
        raw = delta.model_dump_json()
        restored = OrderBookL2Delta.model_validate_json(raw)
        assert restored == delta

    def test_standard_fields(self):
        fields = set(OrderBookL2Delta.model_fields.keys())
        assert {"exchange", "symbol", "timestamp"}.issubset(fields)

    def test_removal_via_zero_quantity(self):
        """quantity=0 means remove the level."""
        delta = OrderBookL2Delta(
            exchange="binance",
            symbol="BTC/USDT",
            timestamp=1711000000001,
            sequence_id=100002,
            asks=[PriceLevel(price=67001.0, quantity=0.0)],
        )
        assert delta.asks[0].quantity == 0.0
