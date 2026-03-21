"""Tests for pnlclaw_backtest.metrics."""

import pytest

from pnlclaw_backtest.metrics import _max_drawdown, compute_metrics
import numpy as np


class TestMaxDrawdown:
    def test_no_drawdown(self) -> None:
        eq = np.array([100.0, 110.0, 120.0, 130.0])
        assert _max_drawdown(eq) == 0.0

    def test_simple_drawdown(self) -> None:
        eq = np.array([100.0, 120.0, 90.0, 110.0])
        # Peak 120, trough 90 → dd = (90 - 120) / 120 = -0.25
        assert _max_drawdown(eq) == pytest.approx(-0.25)

    def test_all_declining(self) -> None:
        eq = np.array([100.0, 80.0, 60.0])
        # (60 - 100) / 100 = -0.40
        assert _max_drawdown(eq) == pytest.approx(-0.40)


class TestComputeMetrics:
    def test_empty_curve(self) -> None:
        m = compute_metrics([], [])
        assert m.total_return == 0.0
        assert m.total_trades == 0

    def test_single_point(self) -> None:
        m = compute_metrics([10000.0], [])
        assert m.total_return == 0.0

    def test_basic_positive_return(self) -> None:
        curve = [10000.0, 10500.0, 11000.0, 11500.0]
        trades = [{"pnl": 500.0}, {"pnl": -200.0}, {"pnl": 300.0}]
        m = compute_metrics(curve, trades)

        assert m.total_return == pytest.approx(0.15, abs=1e-4)
        assert m.max_drawdown == 0.0  # monotonically increasing
        assert m.win_rate == pytest.approx(2 / 3, abs=1e-4)
        assert m.total_trades == 3
        assert m.profit_factor == pytest.approx(800.0 / 200.0, abs=1e-4)

    def test_sharpe_ratio_positive(self) -> None:
        # Consistent positive returns should yield positive Sharpe
        curve = [10000.0, 10100.0, 10200.0, 10300.0, 10400.0]
        m = compute_metrics(curve, [], annualization_factor=252)
        assert m.sharpe_ratio > 0

    def test_no_trades_zero_win_rate(self) -> None:
        curve = [10000.0, 10000.0, 10000.0]
        m = compute_metrics(curve, [])
        assert m.win_rate == 0.0
        assert m.profit_factor == 0.0
        assert m.total_trades == 0
