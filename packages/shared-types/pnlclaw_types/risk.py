"""Risk management data models for PnLClaw."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pnlclaw_types.common import Timestamp

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RiskLevel(str, Enum):
    """Four-tier risk classification."""

    SAFE = "safe"
    RESTRICTED = "restricted"
    DANGEROUS = "dangerous"
    BLOCKED = "blocked"


# ---------------------------------------------------------------------------
# RiskRule
# ---------------------------------------------------------------------------


class RiskRule(BaseModel):
    """Definition of a single risk control rule."""

    id: str = Field(..., description="Unique rule identifier")
    name: str = Field(..., min_length=1, description="Human-readable rule name")
    description: str = Field("", description="What this rule checks")
    level: RiskLevel = Field(..., description="Severity level when triggered")
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Rule-specific parameters (e.g. max_position_pct=0.1)",
    )
    enabled: bool = Field(True, description="Whether this rule is active")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "rule-max-pos",
                    "name": "Max Position Size",
                    "description": "Limits single position to 10% of portfolio",
                    "level": "restricted",
                    "parameters": {"max_position_pct": 0.1},
                    "enabled": True,
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# RiskDecision
# ---------------------------------------------------------------------------


class RiskDecision(BaseModel):
    """Result of evaluating a risk rule against a trade intent."""

    rule_id: str = Field(..., description="ID of the rule that was evaluated")
    allowed: bool = Field(..., description="Whether the action is permitted")
    level: RiskLevel = Field(..., description="Risk level of the decision")
    reason: str = Field("", description="Human-readable explanation")
    timestamp: Timestamp = Field(..., description="Decision time (ms epoch)")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "rule_id": "rule-max-pos",
                    "allowed": False,
                    "level": "restricted",
                    "reason": "Position size 15% exceeds max 10%",
                    "timestamp": 1711000000000,
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# RiskAlert
# ---------------------------------------------------------------------------


class RiskAlert(BaseModel):
    """Notification raised when a risk rule is triggered."""

    id: str = Field(..., description="Unique alert identifier")
    rule_id: str = Field(..., description="Triggering rule ID")
    level: RiskLevel = Field(..., description="Alert severity")
    message: str = Field(..., description="Alert message")
    context: dict[str, Any] = Field(
        default_factory=dict, description="Additional context about the alert"
    )
    timestamp: Timestamp = Field(..., description="Alert time (ms epoch)")
    acknowledged: bool = Field(False, description="Whether the user has acknowledged this alert")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "alert-001",
                    "rule_id": "rule-max-pos",
                    "level": "restricted",
                    "message": "Position size exceeds limit",
                    "context": {"symbol": "BTC/USDT", "requested_pct": 0.15},
                    "timestamp": 1711000000000,
                    "acknowledged": False,
                }
            ]
        }
    )
