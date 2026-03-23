"""Backtest feedback — manual analysis and improvement suggestions (v0.1)."""

from __future__ import annotations

from pnlclaw_agent.feedback.analyzer import ResultAnalyzer
from pnlclaw_agent.feedback.loop import BacktestFeedbackLoop
from pnlclaw_agent.feedback.suggestions import (
    FeedbackReport,
    StrategyImprovement,
    SuggestionGenerator,
    apply_suggestion,
)

__all__ = [
    "BacktestFeedbackLoop",
    "FeedbackReport",
    "ResultAnalyzer",
    "StrategyImprovement",
    "SuggestionGenerator",
    "apply_suggestion",
]
