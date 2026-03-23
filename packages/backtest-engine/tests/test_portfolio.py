"""Tests for pnlclaw_backtest.portfolio."""

import pytest

from pnlclaw_backtest.portfolio import Portfolio
from pnlclaw_types.trading import Fill, OrderSide


def _make_fill(price: float = 100.0, quantity: float = 1.0, fee: float = 0.0) -> Fill:
    return Fill(
        id="fill-001",
        order_id="ord-001",
        price=price,
        quantity=quantity,
        fee=fee,
        timestamp=1711000000000,
    )


class TestPortfolio:
    def test_initial_state(self) -> None:
        p = Portfolio(initial_cash=10_000.0)
        assert p.cash == 10_000.0
        assert p.positions == {}
        assert p.get_equity_curve() == []

    def test_buy_decreases_cash(self) -> None:
        p = Portfolio(initial_cash=10_000.0)
        fill = _make_fill(price=100.0, quantity=2.0, fee=1.0)
        p.apply_fill(fill, OrderSide.BUY)

        assert p.cash == pytest.approx(10_000.0 - 200.0 - 1.0)
        assert p.get_position_quantity("BTC/USDT") == pytest.approx(2.0)

    def test_sell_increases_cash(self) -> None:
        p = Portfolio(initial_cash=10_000.0)
        # Buy first
        p.apply_fill(_make_fill(price=100.0, quantity=2.0), OrderSide.BUY)
        # Sell
        p.apply_fill(_make_fill(price=110.0, quantity=2.0, fee=0.5), OrderSide.SELL)

        assert p.cash == pytest.approx(10_000.0 - 200.0 + 220.0 - 0.5)
        assert p.get_position_quantity("BTC/USDT") == pytest.approx(0.0)

    def test_equity_curve_updates(self) -> None:
        p = Portfolio(initial_cash=10_000.0)
        p.apply_fill(_make_fill(price=100.0, quantity=1.0), OrderSide.BUY)

        p.update_equity("BTC/USDT", 100.0)
        p.update_equity("BTC/USDT", 110.0)
        p.update_equity("BTC/USDT", 105.0)

        curve = p.get_equity_curve()
        assert len(curve) == 3
        assert curve[0] == pytest.approx(9900.0 + 100.0)  # 10000
        assert curve[1] == pytest.approx(9900.0 + 110.0)  # 10010
        assert curve[2] == pytest.approx(9900.0 + 105.0)  # 10005

    def test_reset(self) -> None:
        p = Portfolio(initial_cash=5_000.0)
        p.apply_fill(_make_fill(price=100.0, quantity=1.0), OrderSide.BUY)
        p.update_equity("BTC/USDT", 100.0)

        p.reset()

        assert p.cash == 5_000.0
        assert p.positions == {}
        assert p.get_equity_curve() == []
