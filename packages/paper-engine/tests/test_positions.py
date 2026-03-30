"""Tests for PositionManager with USDT-based quantities (S2-G04)."""

from __future__ import annotations

import time

import pytest

from pnlclaw_paper.positions import PositionManager
from pnlclaw_types.trading import Fill, MarginMode, OrderSide, PositionSide


def _make_fill(price: float, usdt_notional: float, order_id: str = "ord-1") -> Fill:
    """Create a fill. ``usdt_notional`` is the USDT amount (not base qty)."""
    return Fill(
        id=f"fill-{int(time.time() * 1000)}",
        order_id=order_id,
        price=price,
        quantity=usdt_notional,
        fee=0.0,
        fee_currency="USDT",
        timestamp=int(time.time() * 1000),
    )


class TestPositionManager:
    def test_new_long_position(self) -> None:
        mgr = PositionManager()
        fill = _make_fill(67000.0, 67000.0)
        pos, realized = mgr.apply_fill_with_symbol(
            "acc-1", "BTC-USDT-SWAP", fill, OrderSide.BUY,
            leverage=10, margin_mode=MarginMode.CROSS, pos_side=PositionSide.LONG,
        )
        assert pos.side == OrderSide.BUY
        assert pos.quantity == 67000.0
        assert pos.quantity_base == pytest.approx(1.0)
        assert pos.avg_entry_price == 67000.0
        assert pos.leverage == 10
        assert pos.margin == pytest.approx(6700.0)
        assert realized == 0.0

    def test_increase_long_position(self) -> None:
        mgr = PositionManager()
        f1 = _make_fill(66000.0, 66000.0)
        f2 = _make_fill(68000.0, 68000.0)
        mgr.apply_fill_with_symbol(
            "acc-1", "BTC-USDT-SWAP", f1, OrderSide.BUY,
            leverage=10, pos_side=PositionSide.LONG,
        )
        pos, realized = mgr.apply_fill_with_symbol(
            "acc-1", "BTC-USDT-SWAP", f2, OrderSide.BUY,
            leverage=10, pos_side=PositionSide.LONG,
        )
        assert pos.quantity == pytest.approx(134000.0)
        assert pos.quantity_base == pytest.approx(2.0)
        assert pos.avg_entry_price == pytest.approx(67000.0)
        assert realized == 0.0

    def test_close_long_with_profit(self) -> None:
        mgr = PositionManager()
        f1 = _make_fill(66000.0, 66000.0)
        mgr.apply_fill_with_symbol(
            "acc-1", "BTC-USDT-SWAP", f1, OrderSide.BUY,
            leverage=10, pos_side=PositionSide.LONG,
        )
        f2 = _make_fill(68000.0, 66000.0)
        pos, realized = mgr.apply_fill_with_symbol(
            "acc-1", "BTC-USDT-SWAP", f2, OrderSide.SELL,
            leverage=10, pos_side=PositionSide.LONG,
        )
        assert pos.quantity == pytest.approx(0.0, abs=1)
        assert realized == pytest.approx(2000.0)

    def test_close_long_with_loss(self) -> None:
        mgr = PositionManager()
        f1 = _make_fill(68000.0, 68000.0)
        mgr.apply_fill_with_symbol(
            "acc-1", "BTC-USDT-SWAP", f1, OrderSide.BUY,
            leverage=10, pos_side=PositionSide.LONG,
        )
        f2 = _make_fill(66000.0, 68000.0)
        _, realized = mgr.apply_fill_with_symbol(
            "acc-1", "BTC-USDT-SWAP", f2, OrderSide.SELL,
            leverage=10, pos_side=PositionSide.LONG,
        )
        assert realized == pytest.approx(-2000.0)

    def test_partial_close(self) -> None:
        mgr = PositionManager()
        f1 = _make_fill(67000.0, 67000.0)
        mgr.apply_fill_with_symbol(
            "acc-1", "BTC-USDT-SWAP", f1, OrderSide.BUY,
            leverage=10, pos_side=PositionSide.LONG,
        )
        f2 = _make_fill(68000.0, 33500.0)
        pos, realized = mgr.apply_fill_with_symbol(
            "acc-1", "BTC-USDT-SWAP", f2, OrderSide.SELL,
            leverage=10, pos_side=PositionSide.LONG,
        )
        assert pos.quantity == pytest.approx(33500.0)
        assert realized == pytest.approx(500.0)

    def test_short_position(self) -> None:
        mgr = PositionManager()
        f1 = _make_fill(67000.0, 67000.0)
        mgr.apply_fill_with_symbol(
            "acc-1", "BTC-USDT-SWAP", f1, OrderSide.SELL,
            leverage=10, pos_side=PositionSide.SHORT,
        )
        pos = mgr.get_position("acc-1", "BTC-USDT-SWAP")
        assert pos is not None
        assert pos.side == OrderSide.SELL

    def test_close_short_with_profit(self) -> None:
        mgr = PositionManager()
        f1 = _make_fill(68000.0, 68000.0)
        mgr.apply_fill_with_symbol(
            "acc-1", "BTC-USDT-SWAP", f1, OrderSide.SELL,
            leverage=10, pos_side=PositionSide.SHORT,
        )
        f2 = _make_fill(66000.0, 68000.0)
        _, realized = mgr.apply_fill_with_symbol(
            "acc-1", "BTC-USDT-SWAP", f2, OrderSide.BUY,
            leverage=10, pos_side=PositionSide.SHORT,
        )
        assert realized == pytest.approx(2000.0)

    def test_isolated_margin_has_liquidation_price(self) -> None:
        mgr = PositionManager()
        f1 = _make_fill(67000.0, 67000.0)
        pos, _ = mgr.apply_fill_with_symbol(
            "acc-1", "BTC-USDT-SWAP", f1, OrderSide.BUY,
            leverage=10, margin_mode=MarginMode.ISOLATED, pos_side=PositionSide.LONG,
        )
        assert pos.liquidation_price is not None
        assert pos.liquidation_price < 67000.0

    def test_cross_margin_has_estimated_liquidation_price(self) -> None:
        mgr = PositionManager()
        f1 = _make_fill(67000.0, 67000.0)
        pos, _ = mgr.apply_fill_with_symbol(
            "acc-1", "BTC-USDT-SWAP", f1, OrderSide.BUY,
            leverage=10, margin_mode=MarginMode.CROSS, pos_side=PositionSide.LONG,
        )
        assert pos.liquidation_price is not None
        assert pos.liquidation_price < 67000.0

    def test_liq_price_recalculated_on_add_position(self) -> None:
        """Liq price must update when adding to a position (not stay at first value)."""
        mgr = PositionManager()
        f1 = _make_fill(67000.0, 67000.0)
        pos1, _ = mgr.apply_fill_with_symbol(
            "acc-1", "BTC-USDT-SWAP", f1, OrderSide.BUY,
            leverage=10, margin_mode=MarginMode.ISOLATED, pos_side=PositionSide.LONG,
        )
        liq_1 = pos1.liquidation_price

        f2 = _make_fill(68000.0, 68000.0)
        pos2, _ = mgr.apply_fill_with_symbol(
            "acc-1", "BTC-USDT-SWAP", f2, OrderSide.BUY,
            leverage=10, margin_mode=MarginMode.ISOLATED, pos_side=PositionSide.LONG,
        )
        liq_2 = pos2.liquidation_price

        assert liq_1 is not None
        assert liq_2 is not None
        assert liq_1 != liq_2

    def test_cross_margin_liq_with_balance(self) -> None:
        """Cross-margin liq price uses available_balance for better estimate."""
        mgr = PositionManager()
        f1 = _make_fill(67000.0, 67000.0)
        pos, _ = mgr.apply_fill_with_symbol(
            "acc-1", "BTC-USDT-SWAP", f1, OrderSide.BUY,
            leverage=10, margin_mode=MarginMode.CROSS, pos_side=PositionSide.LONG,
            available_balance=100000.0,
        )
        assert pos.liquidation_price is not None
        assert pos.liquidation_price < 67000.0

    def test_unrealized_pnl_long(self) -> None:
        mgr = PositionManager()
        f1 = _make_fill(67000.0, 67000.0)
        mgr.apply_fill_with_symbol(
            "acc-1", "BTC-USDT-SWAP", f1, OrderSide.BUY,
            leverage=10, pos_side=PositionSide.LONG,
        )
        updated = mgr.update_unrealized_pnl("acc-1", "BTC-USDT-SWAP", 68000.0)
        assert len(updated) == 1
        assert updated[0].unrealized_pnl == pytest.approx(1000.0)
        assert updated[0].current_price == 68000.0

    def test_unrealized_pnl_short(self) -> None:
        mgr = PositionManager()
        f1 = _make_fill(67000.0, 67000.0)
        mgr.apply_fill_with_symbol(
            "acc-1", "BTC-USDT-SWAP", f1, OrderSide.SELL,
            leverage=10, pos_side=PositionSide.SHORT,
        )
        updated = mgr.update_unrealized_pnl("acc-1", "BTC-USDT-SWAP", 66000.0)
        assert len(updated) == 1
        assert updated[0].unrealized_pnl == pytest.approx(1000.0)

    def test_get_open_positions(self) -> None:
        mgr = PositionManager()
        f1 = _make_fill(67000.0, 67000.0)
        mgr.apply_fill_with_symbol(
            "acc-1", "BTC-USDT-SWAP", f1, OrderSide.BUY,
            leverage=10, pos_side=PositionSide.LONG,
        )
        f2 = _make_fill(3000.0, 30000.0)
        mgr.apply_fill_with_symbol(
            "acc-1", "ETH-USDT-SWAP", f2, OrderSide.BUY,
            leverage=10, pos_side=PositionSide.LONG,
        )
        f3 = _make_fill(68000.0, 67000.0)
        mgr.apply_fill_with_symbol(
            "acc-1", "BTC-USDT-SWAP", f3, OrderSide.SELL,
            leverage=10, pos_side=PositionSide.LONG,
        )
        open_pos = mgr.get_open_positions("acc-1")
        assert len(open_pos) == 1
        assert open_pos[0].symbol == "ETH-USDT-SWAP"

    def test_serialization_roundtrip(self) -> None:
        mgr = PositionManager()
        f1 = _make_fill(67000.0, 67000.0)
        mgr.apply_fill_with_symbol(
            "acc-1", "BTC-USDT-SWAP", f1, OrderSide.BUY,
            leverage=10, pos_side=PositionSide.LONG,
        )
        data = mgr.get_all_data()

        mgr2 = PositionManager()
        mgr2.load_data(data)
        pos = mgr2.get_position("acc-1", "BTC-USDT-SWAP")
        assert pos is not None
        assert pos.quantity == pytest.approx(67000.0)
        assert pos.leverage == 10
