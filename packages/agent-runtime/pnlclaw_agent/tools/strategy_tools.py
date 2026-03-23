"""Strategy tools — validate, backtest run, and backtest result lookup.

``StrategyValidateTool`` validates a strategy config using the strategy
engine validator.  ``BacktestRunTool`` compiles and runs a backtest.
``BacktestResultTool`` retrieves a previously run backtest result.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from pydantic import ValidationError

from pnlclaw_agent.tools.base import BaseTool, ToolResult
from pnlclaw_types.risk import RiskLevel
from pnlclaw_types.strategy import BacktestResult

# ---------------------------------------------------------------------------
# Shared backtest results store
# ---------------------------------------------------------------------------

# In-memory store shared between BacktestRunTool and BacktestResultTool.
# Populated by BacktestRunTool, queried by BacktestResultTool.
_backtest_results: dict[str, BacktestResult] = {}


def get_results_store() -> dict[str, BacktestResult]:
    """Return the shared in-memory backtest results store."""
    return _backtest_results


# ---------------------------------------------------------------------------
# StrategyValidateTool
# ---------------------------------------------------------------------------


class StrategyValidateTool(BaseTool):
    """Validate a strategy configuration for correctness."""

    @property
    def name(self) -> str:
        return "strategy_validate"

    @property
    def description(self) -> str:
        return (
            "Validate a strategy configuration, checking parameter ranges, "
            "logic consistency, and indicator availability."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "config": {
                    "type": "object",
                    "description": "Strategy configuration dict (StrategyConfig fields)",
                },
            },
            "required": ["config"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.SAFE

    def execute(self, args: dict[str, Any]) -> ToolResult:
        config_dict = args.get("config")
        if not config_dict or not isinstance(config_dict, dict):
            return ToolResult(output="", error="Missing or invalid 'config' parameter")

        try:
            from pnlclaw_strategy.models import EngineStrategyConfig

            engine_config = EngineStrategyConfig.model_validate(config_dict)
        except (ValidationError, Exception) as exc:
            return ToolResult(
                output=f"Strategy config parsing failed:\n{exc}",
                error="Invalid strategy configuration",
            )

        from pnlclaw_strategy.validator import validate

        result = validate(engine_config)

        if result.valid:
            return ToolResult(
                output=f"Strategy '{engine_config.name}' is valid. All checks passed."
            )

        errors_text = "\n".join(f"  - {e}" for e in result.errors)
        return ToolResult(
            output=(
                f"Strategy '{engine_config.name}' has {len(result.errors)} "
                f"validation error(s):\n{errors_text}"
            )
        )


# ---------------------------------------------------------------------------
# BacktestRunTool
# ---------------------------------------------------------------------------


class BacktestRunTool(BaseTool):
    """Run a backtest with a given strategy config and kline data."""

    def __init__(self, backtest_engine: Any) -> None:
        self._engine = backtest_engine

    @property
    def name(self) -> str:
        return "backtest_run"

    @property
    def description(self) -> str:
        return (
            "Run a backtest simulation with a strategy configuration and "
            "historical kline data. Returns performance metrics including "
            "total return, Sharpe ratio, max drawdown, and win rate."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "strategy_config": {
                    "type": "object",
                    "description": "Strategy configuration dict",
                },
                "data": {
                    "type": "array",
                    "description": (
                        "List of OHLCV dicts with keys: timestamp, open, high, low, close, volume"
                    ),
                },
            },
            "required": ["strategy_config", "data"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.RESTRICTED

    def execute(self, args: dict[str, Any]) -> ToolResult:
        config_dict = args.get("strategy_config")
        data_list = args.get("data")

        if not config_dict or not isinstance(config_dict, dict):
            return ToolResult(output="", error="Missing or invalid 'strategy_config'")
        if not data_list or not isinstance(data_list, list):
            return ToolResult(output="", error="Missing or invalid 'data'")
        if len(data_list) < 2:
            return ToolResult(output="", error="Need at least 2 kline bars for backtest")

        # Compile strategy
        try:
            from pnlclaw_strategy.compiler import compile as compile_strategy
            from pnlclaw_strategy.models import EngineStrategyConfig

            engine_config = EngineStrategyConfig.model_validate(config_dict)
            strategy_runtime = compile_strategy(engine_config)
        except Exception as exc:
            return ToolResult(
                output=f"Strategy compilation failed: {exc}",
                error="Strategy compilation error",
            )

        # Convert data to DataFrame
        try:
            df = pd.DataFrame(data_list)
            required_cols = {"timestamp", "open", "high", "low", "close", "volume"}
            missing = required_cols - set(df.columns)
            if missing:
                return ToolResult(
                    output="",
                    error=f"Data missing required columns: {sorted(missing)}",
                )
        except Exception as exc:
            return ToolResult(output=f"Data conversion failed: {exc}", error="Data error")

        # Run backtest
        try:
            result: BacktestResult = self._engine.run(strategy_runtime, df)
        except Exception as exc:
            return ToolResult(output=f"Backtest execution failed: {exc}", error="Backtest error")

        # Store result
        _backtest_results[result.id] = result

        # Format output
        m = result.metrics
        lines = [
            f"Backtest Complete — ID: {result.id}",
            f"  Strategy: {result.strategy_id}",
            f"  Period: {result.start_date:%Y-%m-%d} to {result.end_date:%Y-%m-%d}",
            f"  Trades: {result.trades_count}",
            "",
            "  Performance Metrics:",
            f"    Total Return: {m.total_return:+.2%}",
            f"    Annual Return: {m.annual_return:+.2%}",
            f"    Sharpe Ratio: {m.sharpe_ratio:.2f}",
            f"    Max Drawdown: {m.max_drawdown:.2%}",
            f"    Win Rate: {m.win_rate:.1%}",
            f"    Profit Factor: {m.profit_factor:.2f}",
        ]
        return ToolResult(output="\n".join(lines))


# ---------------------------------------------------------------------------
# BacktestResultTool
# ---------------------------------------------------------------------------


class BacktestResultTool(BaseTool):
    """Look up a previously run backtest result by ID."""

    def __init__(self, results_store: dict[str, BacktestResult] | None = None) -> None:
        self._store = results_store if results_store is not None else _backtest_results

    @property
    def name(self) -> str:
        return "backtest_result"

    @property
    def description(self) -> str:
        return (
            "Retrieve a previously run backtest result by its ID, "
            "showing performance metrics and trade count."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "backtest_id": {
                    "type": "string",
                    "description": "The backtest run ID to look up",
                },
            },
            "required": ["backtest_id"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.SAFE

    def execute(self, args: dict[str, Any]) -> ToolResult:
        backtest_id = args.get("backtest_id", "")
        if not backtest_id:
            return ToolResult(output="", error="Missing required parameter: backtest_id")

        result = self._store.get(backtest_id)
        if result is None:
            available = list(self._store.keys())[:5]
            hint = f" Available IDs: {available}" if available else ""
            return ToolResult(output=f"No backtest found with ID '{backtest_id}'.{hint}")

        m = result.metrics
        lines = [
            f"Backtest Result — ID: {result.id}",
            f"  Strategy: {result.strategy_id}",
            f"  Period: {result.start_date:%Y-%m-%d} to {result.end_date:%Y-%m-%d}",
            f"  Trades: {result.trades_count}",
            "",
            "  Performance Metrics:",
            f"    Total Return: {m.total_return:+.2%}",
            f"    Annual Return: {m.annual_return:+.2%}",
            f"    Sharpe Ratio: {m.sharpe_ratio:.2f}",
            f"    Max Drawdown: {m.max_drawdown:.2%}",
            f"    Win Rate: {m.win_rate:.1%}",
            f"    Profit Factor: {m.profit_factor:.2f}",
        ]
        return ToolResult(output="\n".join(lines))
