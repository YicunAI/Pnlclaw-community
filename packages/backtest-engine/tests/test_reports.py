"""Tests for pnlclaw_backtest.reports."""

import json

from pnlclaw_backtest.reports import to_dict, to_json
from pnlclaw_types.strategy import BacktestMetrics, BacktestResult


def _make_result() -> BacktestResult:
    return BacktestResult(
        id="bt-test-001",
        strategy_id="strat-001",
        start_date="2025-01-01T00:00:00",
        end_date="2025-03-31T23:59:59",
        metrics=BacktestMetrics(
            total_return=0.15,
            annual_return=0.45,
            sharpe_ratio=1.8,
            max_drawdown=-0.08,
            win_rate=0.55,
            profit_factor=1.6,
            total_trades=42,
        ),
        equity_curve=[10000.0, 10500.0, 11500.0],
        trades_count=42,
        created_at=1711000000000,
    )


class TestToJson:
    def test_valid_json(self) -> None:
        result = _make_result()
        output = to_json(result)
        parsed = json.loads(output)
        assert parsed["id"] == "bt-test-001"
        assert parsed["metrics"]["total_return"] == 0.15
        assert parsed["equity_curve"] == [10000.0, 10500.0, 11500.0]

    def test_dates_are_iso_strings(self) -> None:
        result = _make_result()
        parsed = json.loads(to_json(result))
        assert "2025-01-01" in parsed["start_date"]
        assert "2025-03-31" in parsed["end_date"]


class TestToDict:
    def test_returns_dict(self) -> None:
        result = _make_result()
        d = to_dict(result)
        assert isinstance(d, dict)
        assert d["trades_count"] == 42
        assert "metrics" in d
