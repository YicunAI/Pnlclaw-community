"""Tests for PaperOrderManager with state machine (S2-G02)."""

from __future__ import annotations

import pytest

from pnlclaw_types.trading import OrderSide, OrderStatus, OrderType

from pnlclaw_paper.orders import InvalidOrderTransition, PaperOrderManager, can_transition


class TestStateTransitions:
    """Exhaustive state transition tests."""

    def test_valid_transitions(self) -> None:
        assert can_transition(OrderStatus.CREATED, OrderStatus.ACCEPTED) is True
        assert can_transition(OrderStatus.CREATED, OrderStatus.REJECTED) is True
        assert can_transition(OrderStatus.ACCEPTED, OrderStatus.PARTIAL) is True
        assert can_transition(OrderStatus.ACCEPTED, OrderStatus.FILLED) is True
        assert can_transition(OrderStatus.ACCEPTED, OrderStatus.CANCELLED) is True
        assert can_transition(OrderStatus.PARTIAL, OrderStatus.FILLED) is True
        assert can_transition(OrderStatus.PARTIAL, OrderStatus.CANCELLED) is True

    def test_invalid_transitions(self) -> None:
        # Terminal states cannot transition
        assert can_transition(OrderStatus.FILLED, OrderStatus.CREATED) is False
        assert can_transition(OrderStatus.FILLED, OrderStatus.CANCELLED) is False
        assert can_transition(OrderStatus.CANCELLED, OrderStatus.ACCEPTED) is False
        assert can_transition(OrderStatus.REJECTED, OrderStatus.ACCEPTED) is False
        # Skip states
        assert can_transition(OrderStatus.CREATED, OrderStatus.FILLED) is False
        assert can_transition(OrderStatus.CREATED, OrderStatus.PARTIAL) is False


class TestPaperOrderManager:
    def _make_mgr(self) -> PaperOrderManager:
        return PaperOrderManager()

    def test_place_order_creates_accepted(self) -> None:
        mgr = self._make_mgr()
        order = mgr.place_order(
            "acc-1", symbol="BTC/USDT", side=OrderSide.BUY,
            order_type=OrderType.MARKET, quantity=0.1,
        )
        assert order.status == OrderStatus.ACCEPTED
        assert order.quantity == 0.1

    def test_cancel_order(self) -> None:
        mgr = self._make_mgr()
        order = mgr.place_order(
            "acc-1", symbol="BTC/USDT", side=OrderSide.BUY,
            order_type=OrderType.MARKET, quantity=0.1,
        )
        cancelled = mgr.cancel_order(order.id)
        assert cancelled.status == OrderStatus.CANCELLED

    def test_cancel_filled_raises(self) -> None:
        mgr = self._make_mgr()
        order = mgr.place_order(
            "acc-1", symbol="BTC/USDT", side=OrderSide.BUY,
            order_type=OrderType.MARKET, quantity=0.1,
        )
        mgr.update_fill(order.id, 0.1, 67000.0)
        assert order.status == OrderStatus.FILLED
        with pytest.raises(InvalidOrderTransition):
            mgr.cancel_order(order.id)

    def test_update_fill_partial(self) -> None:
        mgr = self._make_mgr()
        order = mgr.place_order(
            "acc-1", symbol="BTC/USDT", side=OrderSide.BUY,
            order_type=OrderType.MARKET, quantity=1.0,
        )
        mgr.update_fill(order.id, 0.5, 67000.0)
        assert order.status == OrderStatus.PARTIAL
        assert order.filled_quantity == 0.5

    def test_update_fill_complete(self) -> None:
        mgr = self._make_mgr()
        order = mgr.place_order(
            "acc-1", symbol="BTC/USDT", side=OrderSide.BUY,
            order_type=OrderType.MARKET, quantity=0.5,
        )
        mgr.update_fill(order.id, 0.5, 67000.0)
        assert order.status == OrderStatus.FILLED

    def test_weighted_avg_price(self) -> None:
        mgr = self._make_mgr()
        order = mgr.place_order(
            "acc-1", symbol="BTC/USDT", side=OrderSide.BUY,
            order_type=OrderType.MARKET, quantity=1.0,
        )
        mgr.update_fill(order.id, 0.5, 66000.0)
        mgr.update_fill(order.id, 0.5, 68000.0)
        assert order.status == OrderStatus.FILLED
        assert order.avg_fill_price == pytest.approx(67000.0)

    def test_get_orders_by_status(self) -> None:
        mgr = self._make_mgr()
        o1 = mgr.place_order(
            "acc-1", symbol="BTC/USDT", side=OrderSide.BUY,
            order_type=OrderType.MARKET, quantity=0.1,
        )
        o2 = mgr.place_order(
            "acc-1", symbol="ETH/USDT", side=OrderSide.SELL,
            order_type=OrderType.MARKET, quantity=1.0,
        )
        mgr.cancel_order(o2.id)
        accepted = mgr.get_orders("acc-1", status=OrderStatus.ACCEPTED)
        assert len(accepted) == 1
        assert accepted[0].id == o1.id

    def test_get_open_orders(self) -> None:
        mgr = self._make_mgr()
        mgr.place_order(
            "acc-1", symbol="BTC/USDT", side=OrderSide.BUY,
            order_type=OrderType.MARKET, quantity=0.1,
        )
        open_orders = mgr.get_open_orders("acc-1")
        assert len(open_orders) == 1

    def test_order_not_found(self) -> None:
        mgr = self._make_mgr()
        with pytest.raises(KeyError):
            mgr.cancel_order("nonexistent")

    def test_serialization_roundtrip(self) -> None:
        mgr = self._make_mgr()
        mgr.place_order(
            "acc-1", symbol="BTC/USDT", side=OrderSide.BUY,
            order_type=OrderType.LIMIT, quantity=0.5, price=65000.0,
        )
        data = mgr.get_all_data()

        mgr2 = PaperOrderManager()
        mgr2.load_data(data)
        assert len(mgr2.get_orders("acc-1")) == 1
