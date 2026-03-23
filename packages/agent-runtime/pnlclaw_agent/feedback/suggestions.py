"""Improvement suggestions and applying them to engine strategy configs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pnlclaw_agent.feedback.analyzer import (
    ISSUE_EXCESSIVE_DRAWDOWN,
    ISSUE_LOW_WIN_RATE,
    ISSUE_SHARPE_NEGATIVE,
    ISSUE_TOO_FEW_TRADES,
    ISSUE_TOO_MANY_TRADES,
)
from pnlclaw_strategy.models import EngineStrategyConfig
from pnlclaw_types.strategy import BacktestResult


@dataclass
class StrategyImprovement:
    """A single actionable improvement idea derived from backtest feedback."""

    description: str
    category: str  # "parameter_tuning", "add_filter", "timeframe", "risk"
    suggested_changes: dict[str, Any]


@dataclass
class FeedbackReport:
    """Structured output from :class:`BacktestFeedbackLoop`."""

    issues: list[str]
    suggestions: list[StrategyImprovement]
    summary: str
    confidence: float  # 0-1


class SuggestionGenerator:
    """Maps detected issues to concrete improvement suggestions (v0.1 heuristics)."""

    def generate(self, issues: list[str], result: BacktestResult) -> list[StrategyImprovement]:
        """Produce at least one suggestion per issue (categories per sprint spec)."""
        out: list[StrategyImprovement] = []
        for issue in issues:
            out.extend(self._for_issue(issue, result))
        return out

    def _for_issue(self, issue: str, result: BacktestResult) -> list[StrategyImprovement]:
        _ = result  # reserved for future use (e.g. symbol-specific tuning)
        if issue == ISSUE_SHARPE_NEGATIVE:
            return [
                StrategyImprovement(
                    description="Tune signal parameters to improve risk-adjusted returns.",
                    category="parameter_tuning",
                    suggested_changes={
                        "parameters": {"sma_short": 12, "sma_long": 48},
                    },
                )
            ]
        if issue == ISSUE_EXCESSIVE_DRAWDOWN:
            return [
                StrategyImprovement(
                    description="Tighten risk controls to cap drawdown.",
                    category="risk",
                    suggested_changes={
                        "risk_params": {"stop_loss_pct": 0.02, "max_position_pct": 0.05},
                    },
                )
            ]
        if issue == ISSUE_LOW_WIN_RATE:
            return [
                StrategyImprovement(
                    description="Add filter conditions so entries occur in stronger regimes.",
                    category="add_filter",
                    suggested_changes={
                        "entry_rules": {"min_trend_strength": 0.02},
                    },
                )
            ]
        if issue == ISSUE_TOO_FEW_TRADES:
            return [
                StrategyImprovement(
                    description="Use a shorter timeframe or faster parameters "
                    "to increase signal frequency.",
                    category="timeframe",
                    suggested_changes={"interval": "15m"},
                )
            ]
        if issue == ISSUE_TOO_MANY_TRADES:
            return [
                StrategyImprovement(
                    description="Reduce churn via stricter filters or smaller size.",
                    category="add_filter",
                    suggested_changes={
                        "entry_rules": {"cooldown_bars": 4},
                    },
                )
            ]
        return []


def apply_suggestion(
    config: EngineStrategyConfig,
    suggestion: StrategyImprovement,
) -> EngineStrategyConfig:
    """Return a new config with ``suggestion.suggested_changes`` merged in.

    Dict fields ``parameters``, ``entry_rules``, ``exit_rules``, and ``risk_params``
    are shallow-merged when both sides are mappings.
    """
    data = config.model_dump()
    changes = suggestion.suggested_changes

    for key, value in changes.items():
        if key in ("parameters", "entry_rules", "exit_rules", "risk_params") and isinstance(
            value, dict
        ):
            base = data.get(key)
            if isinstance(base, dict):
                merged = {**base, **value}
                data[key] = merged
            else:
                data[key] = dict(value)
        else:
            data[key] = value

    return EngineStrategyConfig.model_validate(data)
