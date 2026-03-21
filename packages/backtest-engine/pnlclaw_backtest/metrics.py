"""Performance metrics for backtesting.

All calculations follow standard quantitative finance definitions:

- **Sharpe Ratio**: ``mean(daily_returns) / std(daily_returns) * sqrt(252)``
  (risk-free rate = 0)
- **Max Drawdown**: largest peak-to-trough decline in the equity curve
- **Win Rate**: winning trades / total trades
- **Profit Factor**: gross profit / gross loss
"""

from __future__ import annotations

import numpy as np

from pnlclaw_types.strategy import BacktestMetrics


def compute_metrics(
    equity_curve: list[float],
    trades: list[dict],
    annualization_factor: int = 252,
) -> BacktestMetrics:
    """Compute performance metrics from an equity curve and trade list.

    Args:
        equity_curve: Equity values at each time step.
        trades: List of trade dicts, each with at least a ``pnl`` key.
        annualization_factor: Trading periods per year (default 252 for
            daily bars; callers can override, e.g. 252*24 for hourly).

    Returns:
        A fully populated ``BacktestMetrics`` model.
    """
    if len(equity_curve) < 2:
        return BacktestMetrics(
            total_return=0.0,
            annual_return=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            profit_factor=0.0,
            total_trades=len(trades),
        )

    eq = np.asarray(equity_curve, dtype=np.float64)

    # --- Returns ---------------------------------------------------------
    returns = np.diff(eq) / eq[:-1]

    # --- Total return ----------------------------------------------------
    total_return = (eq[-1] - eq[0]) / eq[0]

    # --- Annualised return -----------------------------------------------
    n_periods = len(returns)
    if n_periods > 0 and total_return > -1.0:
        annual_return = (1.0 + total_return) ** (annualization_factor / n_periods) - 1.0
    else:
        annual_return = -1.0

    # --- Sharpe Ratio (rf = 0) -------------------------------------------
    mean_ret = float(np.mean(returns))
    std_ret = float(np.std(returns, ddof=1)) if n_periods > 1 else 0.0
    sharpe_ratio = (mean_ret / std_ret * np.sqrt(annualization_factor)) if std_ret > 1e-15 else 0.0

    # --- Maximum Drawdown ------------------------------------------------
    max_drawdown = _max_drawdown(eq)

    # --- Trade statistics ------------------------------------------------
    total_trades = len(trades)
    if total_trades > 0:
        pnls = [t["pnl"] for t in trades]
        wins = sum(1 for p in pnls if p > 0)
        win_rate = wins / total_trades

        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 1e-15 else float("inf")
    else:
        win_rate = 0.0
        profit_factor = 0.0

    return BacktestMetrics(
        total_return=round(total_return, 8),
        annual_return=round(annual_return, 8),
        sharpe_ratio=round(float(sharpe_ratio), 4),
        max_drawdown=round(max_drawdown, 8),
        win_rate=round(win_rate, 4),
        profit_factor=round(profit_factor, 4),
        total_trades=total_trades,
    )


def _max_drawdown(equity: np.ndarray) -> float:
    """Compute the maximum drawdown of an equity curve.

    Returns:
        A non-positive float representing the worst peak-to-trough decline
        as a fraction (e.g. -0.10 for a 10% drawdown).  Returns 0.0 if
        the equity never declined.
    """
    peak = np.maximum.accumulate(equity)
    drawdowns = (equity - peak) / peak
    mdd = float(np.min(drawdowns))
    return min(mdd, 0.0)
