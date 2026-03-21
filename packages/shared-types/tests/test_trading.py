"""Tests for pnlclaw_types.trading — serialization/deserialization roundtrips."""

from pnlclaw_types.trading import (
    Fill,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    PnLRecord,
    Position,
)


class TestOrderEnums:
    def test_order_side_values(self):
        assert OrderSide.BUY == "buy"
        assert OrderSide.SELL == "sell"

    def test_order_type_values(self):
        assert set(OrderType) == {
            OrderType.MARKET,
            OrderType.LIMIT,
            OrderType.STOP_MARKET,
            OrderType.STOP_LIMIT,
        }

    def test_order_status_completeness(self):
        """Spec: created → accepted → partial → filled → cancelled → rejected."""
        expected = {"created", "accepted", "partial", "filled", "cancelled", "rejected"}
        actual = {s.value for s in OrderStatus}
        assert actual == expected


class TestOrder:
    def test_roundtrip(self):
        o = Order(
            id="ord-001",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            quantity=0.5,
            price=67000.0,
            created_at=1711000000000,
            updated_at=1711000000000,
        )
        raw = o.model_dump_json()
        restored = Order.model_validate_json(raw)
        assert restored == o
        assert restored.status == OrderStatus.CREATED

    def test_market_order_no_price(self):
        o = Order(
            id="ord-002",
            symbol="ETH/USDT",
            side=OrderSide.SELL,
            type=OrderType.MARKET,
            quantity=10.0,
            created_at=1711000000000,
            updated_at=1711000000000,
        )
        assert o.price is None


class TestFill:
    def test_roundtrip(self):
        f = Fill(
            id="fill-001",
            order_id="ord-001",
            price=67000.0,
            quantity=0.25,
            fee=0.01675,
            fee_currency="USDT",
            timestamp=1711000001000,
        )
        raw = f.model_dump_json()
        restored = Fill.model_validate_json(raw)
        assert restored == f


class TestPosition:
    def test_roundtrip(self):
        p = Position(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            quantity=0.5,
            avg_entry_price=67000.0,
            unrealized_pnl=150.0,
            opened_at=1711000000000,
            updated_at=1711000050000,
        )
        raw = p.model_dump_json()
        restored = Position.model_validate_json(raw)
        assert restored == p


class TestPnLRecord:
    def test_roundtrip(self):
        r = PnLRecord(
            symbol="BTC/USDT",
            realized_pnl=200.0,
            unrealized_pnl=150.0,
            total_pnl=350.0,
            fees=5.5,
            timestamp=1711000060000,
        )
        raw = r.model_dump_json()
        restored = PnLRecord.model_validate_json(raw)
        assert restored == r
        assert restored.total_pnl == restored.realized_pnl + restored.unrealized_pnl
