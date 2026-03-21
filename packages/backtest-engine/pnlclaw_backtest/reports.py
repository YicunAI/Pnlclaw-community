"""Backtest report generation.

Serializes a ``BacktestResult`` to JSON for storage and API responses.
"""

from __future__ import annotations

import json

from pnlclaw_types.strategy import BacktestResult


def to_json(result: BacktestResult, *, indent: int = 2) -> str:
    """Serialize a ``BacktestResult`` to a JSON string.

    The output includes:
    - Equity curve data points
    - Performance metrics summary
    - Run metadata (dates, strategy ID, trade count)

    Args:
        result: A completed backtest result.
        indent: JSON indentation level (default 2).

    Returns:
        A JSON string representation of the backtest result.
    """
    payload = _build_report_dict(result)
    return json.dumps(payload, indent=indent, default=str)


def to_dict(result: BacktestResult) -> dict:
    """Convert a ``BacktestResult`` to a plain dict for API responses.

    Args:
        result: A completed backtest result.

    Returns:
        A JSON-serializable dictionary.
    """
    return _build_report_dict(result)


def _build_report_dict(result: BacktestResult) -> dict:
    """Build the canonical report dictionary."""
    return {
        "id": result.id,
        "strategy_id": result.strategy_id,
        "start_date": result.start_date.isoformat(),
        "end_date": result.end_date.isoformat(),
        "trades_count": result.trades_count,
        "created_at": result.created_at,
        "metrics": {
            "total_return": result.metrics.total_return,
            "annual_return": result.metrics.annual_return,
            "sharpe_ratio": result.metrics.sharpe_ratio,
            "max_drawdown": result.metrics.max_drawdown,
            "win_rate": result.metrics.win_rate,
            "profit_factor": result.metrics.profit_factor,
            "total_trades": result.metrics.total_trades,
        },
        "equity_curve": result.equity_curve,
    }
