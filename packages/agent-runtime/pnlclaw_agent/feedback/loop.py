"""Manual backtest feedback loop (v0.1 — analyze only, no auto re-run)."""

from __future__ import annotations

from pnlclaw_agent.feedback.analyzer import ResultAnalyzer
from pnlclaw_agent.feedback.suggestions import FeedbackReport, SuggestionGenerator
from pnlclaw_types.strategy import BacktestResult


class BacktestFeedbackLoop:
    """Derive human-readable feedback and improvement ideas from a backtest."""

    def __init__(self) -> None:
        self._analyzer = ResultAnalyzer()
        self._suggestions = SuggestionGenerator()

    def analyze(self, result: BacktestResult) -> FeedbackReport:
        """Inspect metrics and trade counts, then emit issues and suggestions."""
        issues = self._analyzer.detect_issues(result)
        suggestions = self._suggestions.generate(issues, result)
        summary = self._build_summary(issues, result)
        confidence = self._confidence(issues)
        return FeedbackReport(
            issues=issues,
            suggestions=suggestions,
            summary=summary,
            confidence=confidence,
        )

    def _build_summary(self, issues: list[str], result: BacktestResult) -> str:
        m = result.metrics
        trades = result.trades_count if result.trades_count else m.total_trades
        if not issues:
            return (
                f"Backtest {result.id}: no major v0.1 threshold breaches "
                f"(Sharpe={m.sharpe_ratio:.2f}, MDD={m.max_drawdown:.2%}, "
                f"win_rate={m.win_rate:.2%}, trades={trades})."
            )
        return (
            f"Backtest {result.id}: found {len(issues)} issue(s) — "
            f"Sharpe={m.sharpe_ratio:.2f}, MDD={m.max_drawdown:.2%}, "
            f"win_rate={m.win_rate:.2%}, trades={trades}."
        )

    def _confidence(self, issues: list[str]) -> float:
        """Heuristic confidence in the diagnostic (more issues → lower score)."""
        if not issues:
            return 1.0
        # Penalize each issue slightly, floor at 0.15
        score = 1.0 - 0.12 * len(issues)
        return max(0.15, min(1.0, score))
