"""Risk engine — pre-trade risk checks against configurable rules.

Loads all enabled rules and evaluates a TradeIntent against each.
If any rule blocks, the overall decision is denied.
"""

from __future__ import annotations

import time
from typing import Any, Protocol

from pnlclaw_types.agent import TradeIntent
from pnlclaw_types.risk import RiskDecision, RiskLevel


class RiskRuleProtocol(Protocol):
    """Contract that every risk rule must satisfy."""

    @property
    def rule_id(self) -> str: ...

    @property
    def enabled(self) -> bool: ...

    def check(self, intent: TradeIntent, context: dict[str, Any]) -> RiskDecision: ...


class RiskEngine:
    """Central risk engine that evaluates a TradeIntent against all rules.

    Args:
        rules: Ordered list of risk rules to evaluate.
    """

    def __init__(self, rules: list[RiskRuleProtocol] | None = None) -> None:
        self._rules: list[RiskRuleProtocol] = list(rules) if rules else []

    def add_rule(self, rule: RiskRuleProtocol) -> None:
        """Register a new risk rule."""
        self._rules.append(rule)

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by ID. Returns True if found and removed."""
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.rule_id != rule_id]
        return len(self._rules) < before

    @property
    def rules(self) -> list[RiskRuleProtocol]:
        """All registered rules."""
        return list(self._rules)

    def pre_check(self, intent: TradeIntent, context: dict[str, Any] | None = None) -> RiskDecision:
        """Run all enabled rules against a TradeIntent.

        Returns a single aggregated RiskDecision.  If any rule blocks,
        the overall decision is denied with the blocking rule's reason.

        Args:
            intent: The trade intent to evaluate.
            context: Runtime context (positions, balances, recent trades, etc.)

        Returns:
            Aggregated RiskDecision — allowed=True only if every rule passes.
        """
        ctx = context or {}
        triggered_rules: list[str] = []
        reasons: list[str] = []
        worst_level = RiskLevel.SAFE

        for rule in self._rules:
            if not rule.enabled:
                continue
            decision = rule.check(intent, ctx)
            if not decision.allowed:
                triggered_rules.append(decision.rule_id)
                reasons.append(decision.reason)
                if _level_severity(decision.level) > _level_severity(worst_level):
                    worst_level = decision.level

        now_ms = int(time.time() * 1000)

        if triggered_rules:
            return RiskDecision(
                rule_id=",".join(triggered_rules),
                allowed=False,
                level=worst_level,
                reason="; ".join(reasons),
                timestamp=now_ms,
            )

        return RiskDecision(
            rule_id="all",
            allowed=True,
            level=RiskLevel.SAFE,
            reason="All risk checks passed",
            timestamp=now_ms,
        )


_LEVEL_ORDER = {
    RiskLevel.SAFE: 0,
    RiskLevel.RESTRICTED: 1,
    RiskLevel.DANGEROUS: 2,
    RiskLevel.BLOCKED: 3,
}


def _level_severity(level: RiskLevel) -> int:
    return _LEVEL_ORDER.get(level, 0)
