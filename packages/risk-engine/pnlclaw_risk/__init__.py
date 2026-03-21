"""pnlclaw_risk -- Rule-based risk controls for PnLClaw.

Public API:
    RiskEngine          — central risk evaluation engine
    RiskRuleProtocol    — interface for custom rules
    create_default_rules — factory for the 5 built-in rules
    validate            — TradeIntent validation
    ValidationResult    — validation result type
    KillSwitch          — emergency stop singleton
"""

from pnlclaw_risk.engine import RiskEngine, RiskRuleProtocol
from pnlclaw_risk.kill_switch import KillSwitch
from pnlclaw_risk.rules import (
    CooldownRule,
    DailyLossLimitRule,
    MaxPositionRule,
    MaxSingleRiskRule,
    SymbolBlacklistRule,
    create_default_rules,
)
from pnlclaw_risk.validators import ValidationResult, validate

__all__ = [
    "RiskEngine",
    "RiskRuleProtocol",
    "MaxPositionRule",
    "MaxSingleRiskRule",
    "DailyLossLimitRule",
    "SymbolBlacklistRule",
    "CooldownRule",
    "create_default_rules",
    "validate",
    "ValidationResult",
    "KillSwitch",
]
