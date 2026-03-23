"""Tests for PnL calculation (S2-G05)."""

from __future__ import annotations

import time

import pytest

from pnlclaw_paper.pnl import calculate_account_pnl, calculate_pnl
from pnlclaw_types.trading import OrderSide, Position


def _make_position(
    symbol: str = "BTC/USDT",
    side: OrderSide = OrderSide.BUY,
    quantity: float = 1.0,
    avg_entry: float = 67000.0,
    realized: float = 0.0,
) -> Position:
    now = int(time.time() * 1000)
    return Position(
        symbol=symbol,
        side=side,
        quantity=quantity,
        avg_entry_price=avg_entry,
        unrealized_pnl=0.0,
        realized_pnl=realized,
        opened_at=now,
        updated_at=now,
    )


class TestCalculatePnl:
    def test_long_profit(self) -> None:
        pos = _make_position(side=OrderSide.BUY, avg_entry=67000.0, quantity=1.0)
        record = calculate_pnl(pos, 68000.0)
        assert record.unrealized_pnl == pytest.approx(1000.0)
        assert record.realized_pnl == 0.0
        assert record.total_pnl == pytest.approx(1000.0)

    def test_long_loss(self) -> None:
        pos = _make_position(side=OrderSide.BUY, avg_entry=67000.0, quantity=1.0)
        record = calculate_pnl(pos, 66000.0)
        assert record.unrealized_pnl == pytest.approx(-1000.0)

    def test_short_profit(self) -> None:
        pos = _make_position(side=OrderSide.SELL, avg_entry=67000.0, quantity=1.0)
        record = calculate_pnl(pos, 66000.0)
        assert record.unrealized_pnl == pytest.approx(1000.0)

    def test_short_loss(self) -> None:
        pos = _make_position(side=OrderSide.SELL, avg_entry=67000.0, quantity=1.0)
        record = calculate_pnl(pos, 68000.0)
        assert record.unrealized_pnl == pytest.approx(-1000.0)

    def test_with_realized(self) -> None:
        pos = _make_position(realized=500.0, quantity=0.5, avg_entry=67000.0)
        record = calculate_pnl(pos, 68000.0)
        assert record.realized_pnl == 500.0
        assert record.unrealized_pnl == pytest.approx(500.0)  # 0.5 * 1000
        assert record.total_pnl == pytest.approx(1000.0)  # 500 + 500

    def test_with_fees(self) -> None:
        pos = _make_position(quantity=1.0, avg_entry=67000.0)
        record = calculate_pnl(pos, 68000.0, total_fees=50.0)
        assert record.fees == 50.0
        assert record.total_pnl == pytest.approx(950.0)  # 1000 - 50

    def test_closed_position(self) -> None:
        pos = _make_position(quantity=0.0, realized=2000.0)
        record = calculate_pnl(pos, 68000.0)
        assert record.unrealized_pnl == 0.0
        assert record.realized_pnl == 2000.0
        assert record.total_pnl == pytest.approx(2000.0)


class TestCalculateAccountPnl:
    def test_multiple_positions(self) -> None:
        positions = [
            _make_position("BTC/USDT", OrderSide.BUY, 1.0, 67000.0),
            _make_position("ETH/USDT", OrderSide.BUY, 10.0, 3000.0),
        ]
        prices = {"BTC/USDT": 68000.0, "ETH/USDT": 3100.0}
        records = calculate_account_pnl(positions, prices)
        assert len(records) == 2
        assert records[0].unrealized_pnl == pytest.approx(1000.0)
        assert records[1].unrealized_pnl == pytest.approx(1000.0)

    def test_with_fees_by_symbol(self) -> None:
        positions = [_make_position("BTC/USDT", OrderSide.BUY, 1.0, 67000.0)]
        prices = {"BTC/USDT": 68000.0}
        fees = {"BTC/USDT": 67.0}
        records = calculate_account_pnl(positions, prices, fees)
        assert records[0].fees == 67.0
