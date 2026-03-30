"""Tests for strategy tools (validate, backtest run, backtest result)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pnlclaw_agent.tools.strategy_tools import (
    BacktestResultTool,
    BacktestRunTool,
    StrategyValidateTool,
    get_results_store,
)
from pnlclaw_types.strategy import BacktestMetrics, BacktestResult

# ---------------------------------------------------------------------------
# Mock BacktestEngine
# ---------------------------------------------------------------------------


@dataclass
class MockBacktestEngine:
    """Returns a fixed BacktestResult."""

    def run(self, strategy: Any, data: Any) -> BacktestResult:
        return BacktestResult(
            id="bt-test-001",
            strategy_id="strat-001",
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 3, 31, tzinfo=UTC),
            metrics=BacktestMetrics(
                total_return=0.15,
                annual_return=0.6,
                sharpe_ratio=2.1,
                max_drawdown=-0.05,
                win_rate=0.65,
                profit_factor=2.0,
                total_trades=20,
            ),
            equity_curve=[10000.0, 10500.0, 11000.0, 11500.0],
            trades_count=20,
            created_at=1_700_000_000_000,
        )


# ---------------------------------------------------------------------------
# StrategyValidateTool tests
# ---------------------------------------------------------------------------


class TestStrategyValidateTool:
    def test_valid_strategy(self) -> None:
        tool = StrategyValidateTool()
        config = {
            "id": "strat-001",
            "name": "Test SMA",
            "type": "sma_cross",
            "symbols": ["BTC/USDT"],
            "interval": "1h",
            "parameters": {},
            "entry_rules": {},
            "exit_rules": {},
            "risk_params": {},
        }
        result = tool.execute({"config": config})
        assert result.error is None
        assert "valid" in result.output.lower()

    def test_invalid_config_missing_fields(self) -> None:
        tool = StrategyValidateTool()
        result = tool.execute({"config": {"name": "bad"}})
        # Should fail at parsing
        assert result.error is not None or "failed" in result.output.lower()

    def test_missing_config_param(self) -> None:
        tool = StrategyValidateTool()
        result = tool.execute({})
        assert result.error is not None


# ---------------------------------------------------------------------------
# BacktestRunTool tests
# ---------------------------------------------------------------------------


class TestBacktestRunTool:
    def setup_method(self) -> None:
        # Clear shared results store
        get_results_store().clear()

    def test_sync_execute_rejects(self) -> None:
        """Sync execute() is intentionally blocked; backtest_run is async-only."""
        engine = MockBacktestEngine()
        tool = BacktestRunTool(engine)

        config = {
            "id": "strat-001",
            "name": "Test SMA",
            "type": "sma_cross",
            "symbols": ["BTC/USDT"],
            "interval": "1h",
            "parameters": {"sma_short": 20, "sma_long": 50},
            "entry_rules": {},
            "exit_rules": {},
            "risk_params": {},
        }
        data = [
            {
                "timestamp": i * 3600000,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 10.0,
            }
            for i in range(10)
        ]

        result = tool.execute({"strategy_config": config, "data": data})
        assert result.error is not None
        assert "async" in result.error.lower()

    def test_missing_data(self) -> None:
        tool = BacktestRunTool(MockBacktestEngine())
        result = tool.execute({"strategy_config": {"id": "x"}, "data": []})
        assert result.error is not None

    def test_missing_strategy_config(self) -> None:
        tool = BacktestRunTool(MockBacktestEngine())
        result = tool.execute({"data": [{"a": 1}]})
        assert result.error is not None


# ---------------------------------------------------------------------------
# BacktestResultTool tests
# ---------------------------------------------------------------------------


class TestBacktestResultTool:
    def test_result_found(self) -> None:
        store: dict[str, BacktestResult] = {
            "bt-001": BacktestResult(
                id="bt-001",
                strategy_id="strat-001",
                start_date=datetime(2025, 1, 1, tzinfo=UTC),
                end_date=datetime(2025, 3, 31, tzinfo=UTC),
                metrics=BacktestMetrics(
                    total_return=0.10,
                    annual_return=0.4,
                    sharpe_ratio=1.5,
                    max_drawdown=-0.08,
                    win_rate=0.55,
                    profit_factor=1.3,
                    total_trades=15,
                ),
                equity_curve=[10000.0, 11000.0],
                trades_count=15,
                created_at=1_700_000_000_000,
            ),
        }
        tool = BacktestResultTool(store)
        result = tool.execute({"backtest_id": "bt-001"})
        assert result.error is None
        assert "bt-001" in result.output
        assert "+10.00%" in result.output

    def test_result_not_found(self) -> None:
        tool = BacktestResultTool({})
        result = tool.execute({"backtest_id": "nonexistent"})
        assert "No backtest found" in result.output

    def test_missing_id(self) -> None:
        tool = BacktestResultTool({})
        result = tool.execute({})
        assert result.error is not None
