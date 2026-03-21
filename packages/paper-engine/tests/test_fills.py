"""Tests for fill simulation (S2-G03)."""

from __future__ import annotations

import time

import pytest

from pnlclaw_types.trading import Order, OrderSide, OrderStatus, OrderType

from pnlclaw_paper.fills import try_fill


def _make_order(**overrides) -> Order:
    now = int(time.time() * 1000)
    defaults = {
        "id": "ord-test",
        "symbol": "BTC/USDT",
        "side": OrderSide.BUY,
        "type": OrderType.MARKET,
        "status": OrderStatus.ACCEPTED,
        "quantity": 1.0,
        "price": None,
        "stop_price": None,
        "filled_quantity": 0.0,
        "avg_fill_price": None,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    return Order(**defaults)


class TestTryFill:
    def test_market_buy_fills_immediately(self) -> None:
        order = _make_order(type=OrderType.MARKET, side=OrderSide.BUY)
        fill = try_fill(order, 67000.0)
        assert fill is not None
        assert fill.price == 67000.0
        assert fill.quantity == 1.0

    def test_market_sell_fills_immediately(self) -> None:
        order = _make_order(type=OrderType.MARKET, side=OrderSide.SELL)
        fill = try_fill(order, 67000.0)
        assert fill is not None
        assert fill.price == 67000.0

    def test_limit_buy_fills_at_or_below(self) -> None:
        order = _make_order(type=OrderType.LIMIT, side=OrderSide.BUY, price=66000.0)
        # Price above limit — no fill
        assert try_fill(order, 67000.0) is None
        # Price at limit — fill
        fill = try_fill(order, 66000.0)
        assert fill is not None
        assert fill.price == 66000.0
        # Price below limit — fill
        fill = try_fill(order, 65000.0)
        assert fill is not None

    def test_limit_sell_fills_at_or_above(self) -> None:
        order = _make_order(type=OrderType.LIMIT, side=OrderSide.SELL, price=68000.0)
        # Price below limit — no fill
        assert try_fill(order, 67000.0) is None
        # Price at limit — fill
        fill = try_fill(order, 68000.0)
        assert fill is not None
        # Price above limit — fill
        fill = try_fill(order, 69000.0)
        assert fill is not None

    def test_no_fill_for_wrong_status(self) -> None:
        order = _make_order(status=OrderStatus.CANCELLED)
        assert try_fill(order, 67000.0) is None

    def test_no_fill_for_fully_filled(self) -> None:
        order = _make_order(filled_quantity=1.0)
        assert try_fill(order, 67000.0) is None

    def test_partial_fill_remaining(self) -> None:
        order = _make_order(quantity=2.0, filled_quantity=0.5, status=OrderStatus.PARTIAL)
        fill = try_fill(order, 67000.0)
        assert fill is not None
        assert fill.quantity == 1.5

    def test_fee_calculation(self) -> None:
        order = _make_order()
        fill = try_fill(order, 67000.0, fee_rate=0.001)
        assert fill is not None
        expected_fee = 67000.0 * 1.0 * 0.001
        assert fill.fee == pytest.approx(expected_fee)
