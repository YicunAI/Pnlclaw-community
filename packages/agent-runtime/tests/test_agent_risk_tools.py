"""Tests for risk tools (RiskCheckTool, RiskReportTool)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pnlclaw_agent.tools.risk_tools import RiskCheckTool, RiskReportTool
from pnlclaw_types.agent import TradeIntent
from pnlclaw_types.risk import RiskDecision, RiskLevel

# ---------------------------------------------------------------------------
# Mock rule and engine
# ---------------------------------------------------------------------------


@dataclass
class MockRule:
    rule_id: str = "max_position"
    enabled: bool = True

    def check(self, intent: TradeIntent, context: dict[str, Any]) -> RiskDecision:
        return RiskDecision(
            rule_id=self.rule_id,
            allowed=True,
            level=RiskLevel.SAFE,
            reason="Within limits",
            timestamp=1_700_000_000_000,
        )


@dataclass
class MockRiskEngine:
    _rules: list[MockRule]
    _allow: bool = True

    def __init__(self, rules: list[MockRule] | None = None, allow: bool = True) -> None:
        self._rules = [MockRule()] if rules is None else rules
        self._allow = allow

    @property
    def rules(self) -> list[MockRule]:
        return self._rules

    def pre_check(self, intent: TradeIntent, context: dict[str, Any] | None = None) -> RiskDecision:
        if self._allow:
            return RiskDecision(
                rule_id="all",
                allowed=True,
                level=RiskLevel.SAFE,
                reason="All checks passed",
                timestamp=1_700_000_000_000,
            )
        return RiskDecision(
            rule_id="max_position",
            allowed=False,
            level=RiskLevel.BLOCKED,
            reason="Position size exceeds limit",
            timestamp=1_700_000_000_000,
        )


# ---------------------------------------------------------------------------
# RiskCheckTool tests
# ---------------------------------------------------------------------------

_VALID_INTENT = {
    "symbol": "BTC/USDT",
    "side": "buy",
    "quantity": 0.5,
    "order_type": "market",
    "reasoning": "SMA cross signal",
    "confidence": 0.8,
    "risk_params": {"stop_loss": 0.02},
    "timestamp": 1_700_000_000_000,
}


class TestRiskCheckTool:
    def test_allowed(self) -> None:
        tool = RiskCheckTool(MockRiskEngine(allow=True))
        result = tool.execute({"intent": _VALID_INTENT})
        assert result.error is None
        assert "ALLOWED" in result.output

    def test_blocked(self) -> None:
        tool = RiskCheckTool(MockRiskEngine(allow=False))
        result = tool.execute({"intent": _VALID_INTENT})
        assert result.error is None
        assert "BLOCKED" in result.output
        assert "Position size exceeds limit" in result.output

    def test_invalid_intent(self) -> None:
        tool = RiskCheckTool(MockRiskEngine())
        result = tool.execute({"intent": {"bad": "data"}})
        assert result.error is not None

    def test_missing_intent(self) -> None:
        tool = RiskCheckTool(MockRiskEngine())
        result = tool.execute({})
        assert result.error is not None


# ---------------------------------------------------------------------------
# RiskReportTool tests
# ---------------------------------------------------------------------------


class TestRiskReportTool:
    def test_with_rules(self) -> None:
        rules = [MockRule("rule_a", True), MockRule("rule_b", False)]
        tool = RiskReportTool(MockRiskEngine(rules=rules))
        result = tool.execute({})
        assert result.error is None
        assert "rule_a" in result.output
        assert "rule_b" in result.output
        assert "enabled" in result.output
        assert "disabled" in result.output

    def test_no_rules(self) -> None:
        tool = RiskReportTool(MockRiskEngine(rules=[]))
        result = tool.execute({})
        assert "No risk rules" in result.output
