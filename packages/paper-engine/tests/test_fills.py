"""Tests for fill simulation (S2-G03)."""

from __future__ import annotations

import time

import pytest

from pnlclaw_paper.fills import try_fill
from pnlclaw_types.trading import Order, OrderSide, OrderStatus, OrderType


def _make_order(**overrides) -> Order:
    now = int(time.time() * 1000)
    defaults = {
        "id": "ord-test",
        "symbol": "BTC-USDT-SWAP",
        "side": OrderSide.BUY,
        "type": OrderType.MARKET,
        "status": OrderStatus.ACCEPTED,
        "quantity": 1000.0,
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
        assert fill.quantity == 1000.0

    def test_market_sell_fills_immediately(self) -> None:
        order = _make_order(type=OrderType.MARKET, side=OrderSide.SELL)
        fill = try_fill(order, 67000.0)
        assert fill is not None
        assert fill.price == 67000.0

    def test_limit_buy_fills_at_or_below(self) -> None:
        order = _make_order(type=OrderType.LIMIT, side=OrderSide.BUY, price=66000.0)
        assert try_fill(order, 67000.0) is None
        fill = try_fill(order, 66000.0)
        assert fill is not None
        assert fill.price == 66000.0
        fill = try_fill(order, 65000.0)
        assert fill is not None

    def test_limit_sell_fills_at_or_above(self) -> None:
        order = _make_order(type=OrderType.LIMIT, side=OrderSide.SELL, price=68000.0)
        assert try_fill(order, 67000.0) is None
        fill = try_fill(order, 68000.0)
        assert fill is not None
        fill = try_fill(order, 69000.0)
        assert fill is not None

    def test_no_fill_for_wrong_status(self) -> None:
        order = _make_order(status=OrderStatus.CANCELLED)
        assert try_fill(order, 67000.0) is None

    def test_no_fill_for_fully_filled(self) -> None:
        order = _make_order(filled_quantity=1000.0)
        assert try_fill(order, 67000.0) is None

    def test_partial_fill_remaining(self) -> None:
        order = _make_order(quantity=2000.0, filled_quantity=500.0, status=OrderStatus.PARTIAL)
        fill = try_fill(order, 67000.0)
        assert fill is not None
        assert fill.quantity == 1500.0

    def test_fee_calculation(self) -> None:
        """Fee = USDT notional * fee_rate (quantity is in USDT)."""
        order = _make_order(quantity=1000.0)
        fill = try_fill(order, 67000.0, fee_rate=0.001)
        assert fill is not None
        expected_fee = 1000.0 * 0.001
        assert fill.fee == pytest.approx(expected_fee)

    def test_maker_taker_fee_selection_market(self) -> None:
        """Market orders use taker fee rate."""
        order = _make_order(type=OrderType.MARKET, quantity=10000.0)
        fill = try_fill(order, 67000.0, maker_fee_rate=0.0002, taker_fee_rate=0.0005)
        assert fill is not None
        assert fill.fee == pytest.approx(10000.0 * 0.0005)
        assert fill.fee_rate == pytest.approx(0.0005)
        assert fill.exec_type == "taker"

    def test_maker_taker_fee_selection_limit(self) -> None:
        """Limit orders use maker fee rate."""
        order = _make_order(type=OrderType.LIMIT, side=OrderSide.BUY, price=67000.0, quantity=10000.0)
        fill = try_fill(order, 67000.0, maker_fee_rate=0.0002, taker_fee_rate=0.0005)
        assert fill is not None
        assert fill.fee == pytest.approx(10000.0 * 0.0002)
        assert fill.fee_rate == pytest.approx(0.0002)
        assert fill.exec_type == "maker"

    def test_fill_enriched_fields_present(self) -> None:
        """Fill should contain fee_rate and exec_type fields."""
        order = _make_order(type=OrderType.MARKET, quantity=5000.0)
        fill = try_fill(order, 65000.0, maker_fee_rate=0.0002, taker_fee_rate=0.0005)
        assert fill is not None
        assert hasattr(fill, "fee_rate")
        assert hasattr(fill, "exec_type")
        assert hasattr(fill, "realized_pnl")
        assert hasattr(fill, "symbol")
        assert hasattr(fill, "side")
        assert hasattr(fill, "pos_side")
