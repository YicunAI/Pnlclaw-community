"""Risk management tools — risk check and risk report.

``RiskCheckTool`` evaluates a trade intent against risk rules.
``RiskReportTool`` reports the current state of all risk rules.
"""

from __future__ import annotations

from typing import Any

from pnlclaw_types.agent import TradeIntent
from pnlclaw_types.risk import RiskLevel

from pnlclaw_agent.tools.base import BaseTool, ToolResult


# ---------------------------------------------------------------------------
# RiskCheckTool
# ---------------------------------------------------------------------------


class RiskCheckTool(BaseTool):
    """Check a trade intent against risk management rules."""

    def __init__(self, risk_engine: Any) -> None:
        self._engine = risk_engine

    @property
    def name(self) -> str:
        return "risk_check"

    @property
    def description(self) -> str:
        return (
            "Evaluate a trade intent against all active risk rules. "
            "Returns whether the trade is allowed or blocked, with reasons."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "object",
                    "description": (
                        "Trade intent dict with: symbol, side, quantity, "
                        "order_type, reasoning, confidence, risk_params"
                    ),
                },
            },
            "required": ["intent"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.SAFE

    def execute(self, args: dict[str, Any]) -> ToolResult:
        intent_dict = args.get("intent")
        if not intent_dict or not isinstance(intent_dict, dict):
            return ToolResult(output="", error="Missing or invalid 'intent' parameter")

        try:
            intent = TradeIntent.model_validate(intent_dict)
        except Exception as exc:
            return ToolResult(
                output=f"Invalid trade intent: {exc}",
                error="Failed to parse trade intent",
            )

        try:
            decision = self._engine.pre_check(intent)
        except Exception as exc:
            return ToolResult(output=f"Risk check failed: {exc}", error=str(exc))

        status = "ALLOWED" if decision.allowed else "BLOCKED"
        lines = [
            f"Risk Check Result: {status}",
            f"  Risk Level: {decision.level.value}",
            f"  Rule: {decision.rule_id}",
            f"  Reason: {decision.reason}",
        ]
        return ToolResult(output="\n".join(lines))


# ---------------------------------------------------------------------------
# RiskReportTool
# ---------------------------------------------------------------------------


class RiskReportTool(BaseTool):
    """Generate a report of all active risk rules."""

    def __init__(self, risk_engine: Any) -> None:
        self._engine = risk_engine

    @property
    def name(self) -> str:
        return "risk_report"

    @property
    def description(self) -> str:
        return (
            "List all configured risk management rules with their current "
            "status (enabled/disabled) and descriptions."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.SAFE

    def execute(self, args: dict[str, Any]) -> ToolResult:
        rules = self._engine.rules
        if not rules:
            return ToolResult(output="No risk rules configured.")

        lines = [f"Risk Rules ({len(rules)} total):", ""]
        for rule in rules:
            status = "enabled" if rule.enabled else "disabled"
            lines.append(f"  [{status}] {rule.rule_id}")
        return ToolResult(output="\n".join(lines))
