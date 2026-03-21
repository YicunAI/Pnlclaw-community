"""Strategy and backtesting data models for PnLClaw."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pnlclaw_types.common import Symbol, Timestamp
from pnlclaw_types.trading import OrderSide

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class StrategyType(str, Enum):
    """Built-in strategy archetypes."""

    SMA_CROSS = "sma_cross"
    RSI_REVERSAL = "rsi_reversal"
    MACD = "macd"
    CUSTOM = "custom"


# ---------------------------------------------------------------------------
# StrategyConfig
# ---------------------------------------------------------------------------


class StrategyConfig(BaseModel):
    """Complete strategy definition — serializable to JSON and YAML-compatible."""

    id: str = Field(..., description="Unique strategy identifier")
    name: str = Field(..., min_length=1, description="Human-readable strategy name")
    type: StrategyType = Field(..., description="Strategy archetype")
    description: str = Field("", description="Strategy description")
    symbols: list[Symbol] = Field(
        ..., min_length=1, description="Trading pairs this strategy applies to"
    )
    interval: str = Field(..., description="Kline interval, e.g. '1h', '4h', '1d'")
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Strategy-specific parameters (e.g. sma_short=10, sma_long=50)",
    )
    entry_rules: dict[str, Any] = Field(
        default_factory=dict, description="Entry condition configuration"
    )
    exit_rules: dict[str, Any] = Field(
        default_factory=dict, description="Exit condition configuration"
    )
    risk_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Risk parameters (stop_loss, take_profit, max_position_size, etc.)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "strat-001",
                    "name": "BTC SMA Cross",
                    "type": "sma_cross",
                    "description": "Simple moving average crossover on BTC/USDT",
                    "symbols": ["BTC/USDT"],
                    "interval": "1h",
                    "parameters": {"sma_short": 10, "sma_long": 50},
                    "entry_rules": {"condition": "sma_short > sma_long"},
                    "exit_rules": {"condition": "sma_short < sma_long"},
                    "risk_params": {"stop_loss_pct": 0.02, "max_position_pct": 0.1},
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# Signal
# ---------------------------------------------------------------------------


class Signal(BaseModel):
    """Trading signal emitted by a strategy."""

    strategy_id: str = Field(..., description="Source strategy ID")
    symbol: Symbol = Field(..., description="Target trading pair")
    side: OrderSide = Field(..., description="Signal direction")
    strength: float = Field(
        ..., ge=0.0, le=1.0, description="Signal strength / confidence (0.0 to 1.0)"
    )
    timestamp: Timestamp = Field(..., description="Signal generation time (ms epoch)")
    reason: str = Field("", description="Human-readable reason for the signal")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "strategy_id": "strat-001",
                    "symbol": "BTC/USDT",
                    "side": "buy",
                    "strength": 0.85,
                    "timestamp": 1711000000000,
                    "reason": "SMA 10 crossed above SMA 50",
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# BacktestMetrics
# ---------------------------------------------------------------------------


class BacktestMetrics(BaseModel):
    """Performance metrics from a completed backtest."""

    total_return: float = Field(..., description="Total return as a decimal (0.15 = 15%)")
    annual_return: float = Field(..., description="Annualized return as a decimal")
    sharpe_ratio: float = Field(..., description="Sharpe ratio (risk-free rate = 0)")
    max_drawdown: float = Field(
        ..., le=0, description="Maximum drawdown as a negative decimal (-0.1 = -10%)"
    )
    win_rate: float = Field(
        ..., ge=0, le=1, description="Winning trades / total trades"
    )
    profit_factor: float = Field(
        ..., ge=0, description="Gross profit / gross loss"
    )
    total_trades: int = Field(..., ge=0, description="Total number of trades executed")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "total_return": 0.15,
                    "annual_return": 0.45,
                    "sharpe_ratio": 1.8,
                    "max_drawdown": -0.08,
                    "win_rate": 0.55,
                    "profit_factor": 1.6,
                    "total_trades": 42,
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# BacktestResult
# ---------------------------------------------------------------------------


class BacktestResult(BaseModel):
    """Complete backtest run result."""

    id: str = Field(..., description="Unique backtest run identifier")
    strategy_id: str = Field(..., description="Strategy that was backtested")
    start_date: datetime = Field(..., description="Backtest period start (inclusive)")
    end_date: datetime = Field(..., description="Backtest period end (inclusive)")
    metrics: BacktestMetrics = Field(..., description="Performance metrics")
    equity_curve: list[float] = Field(
        default_factory=list, description="Equity values at each time step"
    )
    trades_count: int = Field(..., ge=0, description="Total trades executed")
    created_at: Timestamp = Field(..., description="When this backtest was run (ms epoch)")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "bt-001",
                    "strategy_id": "strat-001",
                    "start_date": "2025-01-01T00:00:00",
                    "end_date": "2025-03-31T23:59:59",
                    "metrics": {
                        "total_return": 0.15,
                        "annual_return": 0.45,
                        "sharpe_ratio": 1.8,
                        "max_drawdown": -0.08,
                        "win_rate": 0.55,
                        "profit_factor": 1.6,
                        "total_trades": 42,
                    },
                    "equity_curve": [10000.0, 10050.0, 10200.0, 10150.0, 10500.0],
                    "trades_count": 42,
                    "created_at": 1711000000000,
                }
            ]
        }
    )
