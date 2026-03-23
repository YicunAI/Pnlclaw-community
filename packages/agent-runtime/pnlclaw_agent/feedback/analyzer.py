"""Detect common backtest quality issues from metrics."""

from __future__ import annotations

from pnlclaw_types.strategy import BacktestResult

# Issue identifiers — stable strings for tests and logging.
ISSUE_SHARPE_NEGATIVE = "sharpe_negative"
ISSUE_EXCESSIVE_DRAWDOWN = "excessive_drawdown"
ISSUE_LOW_WIN_RATE = "low_win_rate"
ISSUE_TOO_FEW_TRADES = "too_few_trades"
ISSUE_TOO_MANY_TRADES = "too_many_trades"


class ResultAnalyzer:
    """Flags backtest results that fail simple v0.1 quality thresholds."""

    _MDD_THRESHOLD = -0.30  # max_drawdown worse than -30%
    _WIN_RATE_THRESHOLD = 0.30
    _MIN_TRADES = 5
    _MAX_TRADES = 500

    def detect_issues(self, result: BacktestResult) -> list[str]:
        """Return a list of issue identifiers (possibly empty)."""
        issues: list[str] = []
        m = result.metrics
        trades = result.trades_count if result.trades_count else m.total_trades

        if m.sharpe_ratio < 0:
            issues.append(ISSUE_SHARPE_NEGATIVE)

        # max_drawdown is negative (e.g. -0.35 means 35% drawdown)
        if m.max_drawdown < self._MDD_THRESHOLD:
            issues.append(ISSUE_EXCESSIVE_DRAWDOWN)

        if m.win_rate < self._WIN_RATE_THRESHOLD:
            issues.append(ISSUE_LOW_WIN_RATE)

        if trades < self._MIN_TRADES:
            issues.append(ISSUE_TOO_FEW_TRADES)

        if trades > self._MAX_TRADES:
            issues.append(ISSUE_TOO_MANY_TRADES)

        return issues
