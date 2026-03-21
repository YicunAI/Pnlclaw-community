"""Tests for pnlclaw_backtest.commissions."""

import pytest

from pnlclaw_backtest.commissions import NoCommission, PercentageCommission


class TestNoCommission:
    def test_returns_zero(self) -> None:
        c = NoCommission()
        assert c.calculate(100.0, 1.0) == 0.0


class TestPercentageCommission:
    def test_default_rate(self) -> None:
        c = PercentageCommission()  # 0.1%
        fee = c.calculate(10000.0, 1.0)
        assert fee == pytest.approx(10.0)

    def test_custom_rate(self) -> None:
        c = PercentageCommission(rate=0.002)  # 0.2%
        fee = c.calculate(50000.0, 0.5)
        assert fee == pytest.approx(50.0)

    def test_negative_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            PercentageCommission(rate=-0.01)
