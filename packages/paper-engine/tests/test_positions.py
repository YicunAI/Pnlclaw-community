"""Tests for PositionManager (S2-G04)."""

from __future__ import annotations

import time

import pytest

from pnlclaw_paper.positions import PositionManager
from pnlclaw_types.trading import Fill, OrderSide


def _make_fill(price: float, quantity: float, order_id: str = "ord-1") -> Fill:
    return Fill(
        id=f"fill-{int(time.time() * 1000)}",
        order_id=order_id,
        price=price,
        quantity=quantity,
        fee=0.0,
        fee_currency="USDT",
        timestamp=int(time.time() * 1000),
    )


class TestPositionManager:
    def test_new_long_position(self) -> None:
        mgr = PositionManager()
        fill = _make_fill(67000.0, 0.5)
        pos, realized = mgr.apply_fill_with_symbol("acc-1", "BTC/USDT", fill, OrderSide.BUY)
        assert pos.side == OrderSide.BUY
        assert pos.quantity == 0.5
        assert pos.avg_entry_price == 67000.0
        assert realized == 0.0

    def test_increase_long_position(self) -> None:
        mgr = PositionManager()
        f1 = _make_fill(66000.0, 0.5)
        f2 = _make_fill(68000.0, 0.5)
        mgr.apply_fill_with_symbol("acc-1", "BTC/USDT", f1, OrderSide.BUY)
        pos, realized = mgr.apply_fill_with_symbol("acc-1", "BTC/USDT", f2, OrderSide.BUY)
        assert pos.quantity == 1.0
        assert pos.avg_entry_price == pytest.approx(67000.0)
        assert realized == 0.0

    def test_close_long_with_profit(self) -> None:
        mgr = PositionManager()
        f1 = _make_fill(66000.0, 1.0)
        mgr.apply_fill_with_symbol("acc-1", "BTC/USDT", f1, OrderSide.BUY)
        f2 = _make_fill(68000.0, 1.0)
        pos, realized = mgr.apply_fill_with_symbol("acc-1", "BTC/USDT", f2, OrderSide.SELL)
        assert pos.quantity == 0.0
        assert realized == pytest.approx(2000.0)

    def test_close_long_with_loss(self) -> None:
        mgr = PositionManager()
        f1 = _make_fill(68000.0, 1.0)
        mgr.apply_fill_with_symbol("acc-1", "BTC/USDT", f1, OrderSide.BUY)
        f2 = _make_fill(66000.0, 1.0)
        pos, realized = mgr.apply_fill_with_symbol("acc-1", "BTC/USDT", f2, OrderSide.SELL)
        assert realized == pytest.approx(-2000.0)

    def test_partial_close(self) -> None:
        mgr = PositionManager()
        f1 = _make_fill(67000.0, 1.0)
        mgr.apply_fill_with_symbol("acc-1", "BTC/USDT", f1, OrderSide.BUY)
        f2 = _make_fill(68000.0, 0.5)
        pos, realized = mgr.apply_fill_with_symbol("acc-1", "BTC/USDT", f2, OrderSide.SELL)
        assert pos.quantity == 0.5
        assert realized == pytest.approx(500.0)

    def test_short_position(self) -> None:
        mgr = PositionManager()
        f1 = _make_fill(67000.0, 1.0)
        mgr.apply_fill_with_symbol("acc-1", "BTC/USDT", f1, OrderSide.SELL)
        assert mgr.get_position("acc-1", "BTC/USDT").side == OrderSide.SELL

    def test_close_short_with_profit(self) -> None:
        mgr = PositionManager()
        f1 = _make_fill(68000.0, 1.0)
        mgr.apply_fill_with_symbol("acc-1", "BTC/USDT", f1, OrderSide.SELL)
        f2 = _make_fill(66000.0, 1.0)
        pos, realized = mgr.apply_fill_with_symbol("acc-1", "BTC/USDT", f2, OrderSide.BUY)
        assert realized == pytest.approx(2000.0)

    def test_position_flip(self) -> None:
        mgr = PositionManager()
        f1 = _make_fill(67000.0, 0.5)
        mgr.apply_fill_with_symbol("acc-1", "BTC/USDT", f1, OrderSide.BUY)
        f2 = _make_fill(68000.0, 1.0)  # Close 0.5 + open 0.5 short
        pos, realized = mgr.apply_fill_with_symbol("acc-1", "BTC/USDT", f2, OrderSide.SELL)
        assert pos.side == OrderSide.SELL
        assert pos.quantity == 0.5
        assert realized == pytest.approx(500.0)  # profit from closing long

    def test_unrealized_pnl_long(self) -> None:
        mgr = PositionManager()
        f1 = _make_fill(67000.0, 1.0)
        mgr.apply_fill_with_symbol("acc-1", "BTC/USDT", f1, OrderSide.BUY)
        pos = mgr.update_unrealized_pnl("acc-1", "BTC/USDT", 68000.0)
        assert pos is not None
        assert pos.unrealized_pnl == pytest.approx(1000.0)

    def test_unrealized_pnl_short(self) -> None:
        mgr = PositionManager()
        f1 = _make_fill(67000.0, 1.0)
        mgr.apply_fill_with_symbol("acc-1", "BTC/USDT", f1, OrderSide.SELL)
        pos = mgr.update_unrealized_pnl("acc-1", "BTC/USDT", 66000.0)
        assert pos is not None
        assert pos.unrealized_pnl == pytest.approx(1000.0)

    def test_get_open_positions(self) -> None:
        mgr = PositionManager()
        f1 = _make_fill(67000.0, 1.0)
        mgr.apply_fill_with_symbol("acc-1", "BTC/USDT", f1, OrderSide.BUY)
        f2 = _make_fill(3000.0, 10.0)
        mgr.apply_fill_with_symbol("acc-1", "ETH/USDT", f2, OrderSide.BUY)
        # Close BTC
        f3 = _make_fill(68000.0, 1.0)
        mgr.apply_fill_with_symbol("acc-1", "BTC/USDT", f3, OrderSide.SELL)
        open_pos = mgr.get_open_positions("acc-1")
        assert len(open_pos) == 1
        assert open_pos[0].symbol == "ETH/USDT"

    def test_serialization_roundtrip(self) -> None:
        mgr = PositionManager()
        f1 = _make_fill(67000.0, 1.0)
        mgr.apply_fill_with_symbol("acc-1", "BTC/USDT", f1, OrderSide.BUY)
        data = mgr.get_all_data()

        mgr2 = PositionManager()
        mgr2.load_data(data)
        pos = mgr2.get_position("acc-1", "BTC/USDT")
        assert pos is not None
        assert pos.quantity == 1.0
