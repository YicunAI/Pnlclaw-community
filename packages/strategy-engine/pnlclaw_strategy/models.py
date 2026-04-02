"""Strategy engine models — extends shared-types StrategyConfig with engine-specific fields."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field

from pnlclaw_types.strategy import StrategyConfig

# ---------------------------------------------------------------------------
# Rule models for entry/exit/risk configuration
# ---------------------------------------------------------------------------


class ConditionRule(BaseModel):
    """A single condition rule used in entry/exit logic.

    Examples:
        {"indicator": "sma", "params": {"period": 20}, "operator": "crosses_above",
         "comparator": {"indicator": "sma", "params": {"period": 50}}}
    """

    indicator: str = Field(..., description="Indicator name (e.g. 'sma', 'rsi')")
    params: dict[str, Any] = Field(default_factory=dict, description="Indicator parameters (e.g. {'period': 20})")
    operator: str = Field(
        ...,
        description=("Comparison operator: 'crosses_above', 'crosses_below', 'greater_than', 'less_than', 'equal'"),
    )
    comparator: dict[str, Any] | float = Field(
        ...,
        description=(
            "What to compare against — either a numeric value or another indicator dict with 'indicator' and 'params'"
        ),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "indicator": "sma",
                    "params": {"period": 20},
                    "operator": "crosses_above",
                    "comparator": {"indicator": "sma", "params": {"period": 50}},
                }
            ]
        }
    )


class EntryRules(BaseModel):
    """Entry rule configuration for a strategy."""

    long: list[ConditionRule] = Field(
        default_factory=list,
        description="Conditions for opening a long position (all must be true)",
    )
    short: list[ConditionRule] = Field(
        default_factory=list,
        description="Conditions for opening a short position (all must be true)",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "long": [
                        {
                            "indicator": "sma",
                            "params": {"period": 20},
                            "operator": "crosses_above",
                            "comparator": {"indicator": "sma", "params": {"period": 50}},
                        }
                    ],
                    "short": [],
                }
            ]
        }
    )


class ExitRules(BaseModel):
    """Exit rule configuration for a strategy."""

    close_long: list[ConditionRule] = Field(default_factory=list, description="Conditions for closing a long position")
    close_short: list[ConditionRule] = Field(
        default_factory=list, description="Conditions for closing a short position"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "close_long": [
                        {
                            "indicator": "sma",
                            "params": {"period": 20},
                            "operator": "crosses_below",
                            "comparator": {"indicator": "sma", "params": {"period": 50}},
                        }
                    ],
                    "close_short": [],
                }
            ]
        }
    )


class RiskParams(BaseModel):
    """Risk parameter configuration for a strategy."""

    stop_loss_pct: float | None = Field(None, ge=0, le=1, description="Stop loss as decimal (0.02 = 2%)")
    take_profit_pct: float | None = Field(None, ge=0, le=1, description="Take profit as decimal (0.05 = 5%)")
    max_position_pct: float = Field(0.1, ge=0, le=1, description="Maximum position size as fraction of portfolio")
    max_open_positions: int = Field(1, ge=1, description="Maximum concurrent open positions")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "stop_loss_pct": 0.02,
                    "take_profit_pct": 0.05,
                    "max_position_pct": 0.1,
                    "max_open_positions": 1,
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# EngineStrategyConfig — extends StrategyConfig with structured rules
# ---------------------------------------------------------------------------


class EngineStrategyConfig(StrategyConfig):
    """Strategy configuration extended with structured entry/exit/risk rules.

    Inherits all fields from shared-types StrategyConfig (id, name, type,
    description, symbols, interval, parameters, entry_rules, exit_rules,
    risk_params) and adds typed rule parsing for the strategy engine.

    When constructed via ``model_validate``, string-format rules in
    ``entry_rules`` / ``exit_rules`` are automatically parsed into
    ``parsed_entry_rules`` / ``parsed_exit_rules`` if those fields are empty.
    """

    parsed_entry_rules: EntryRules = Field(
        default_factory=EntryRules,
        description="Structured entry rules parsed from entry_rules dict",
    )
    parsed_exit_rules: ExitRules = Field(
        default_factory=ExitRules,
        description="Structured exit rules parsed from exit_rules dict",
    )
    parsed_risk_params: RiskParams = Field(
        default_factory=RiskParams,
        description="Structured risk params parsed from risk_params dict",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "strat-001",
                    "name": "BTC SMA Cross",
                    "type": "sma_cross",
                    "symbols": ["BTC/USDT"],
                    "interval": "1h",
                    "parameters": {"sma_short": 20, "sma_long": 50},
                    "entry_rules": {},
                    "exit_rules": {},
                    "risk_params": {},
                    "parsed_entry_rules": {"long": [], "short": []},
                    "parsed_exit_rules": {"close_long": [], "close_short": []},
                    "parsed_risk_params": {"stop_loss_pct": 0.02, "max_position_pct": 0.1},
                }
            ]
        }
    )

    def model_post_init(self, __context: Any) -> None:
        """Auto-parse string rules from entry_rules/exit_rules if parsed_ variants are empty."""
        from pnlclaw_strategy.rule_parser import parse_entry_rules, parse_exit_rules

        if not self.parsed_entry_rules.long and not self.parsed_entry_rules.short:
            if self.entry_rules:
                parsed = parse_entry_rules(self.entry_rules)
                object.__setattr__(self, "parsed_entry_rules", parsed)

        if not self.parsed_exit_rules.close_long and not self.parsed_exit_rules.close_short:
            if self.exit_rules:
                parsed = parse_exit_rules(self.exit_rules)
                object.__setattr__(self, "parsed_exit_rules", parsed)

        if self.parsed_risk_params == RiskParams() and self.risk_params:
            try:
                parsed_rp = RiskParams.model_validate(self.risk_params)
                object.__setattr__(self, "parsed_risk_params", parsed_rp)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------


class StrategyLoadError(Exception):
    """Raised when a strategy YAML file cannot be loaded or parsed."""


def load_strategy(path: str | Path) -> EngineStrategyConfig:
    """Load a strategy from a YAML file.

    Args:
        path: Path to the YAML strategy file.

    Returns:
        Parsed and validated EngineStrategyConfig.

    Raises:
        StrategyLoadError: If the file cannot be read or parsed.
    """
    path = Path(path)
    if not path.exists():
        raise StrategyLoadError(f"Strategy file not found: {path}")
    if path.suffix.lower() not in (".yaml", ".yml"):
        raise StrategyLoadError(f"Expected .yaml or .yml file, got: {path.suffix}")

    try:
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise StrategyLoadError(f"Invalid YAML in {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise StrategyLoadError(f"Expected a YAML mapping at top level, got {type(data).__name__}")

    # Parse structured sub-sections if present as dicts
    if "entry_rules" in data and isinstance(data["entry_rules"], dict):
        data.setdefault("parsed_entry_rules", data["entry_rules"])
    if "exit_rules" in data and isinstance(data["exit_rules"], dict):
        data.setdefault("parsed_exit_rules", data["exit_rules"])
    if "risk_params" in data and isinstance(data["risk_params"], dict):
        data.setdefault("parsed_risk_params", data["risk_params"])

    try:
        return EngineStrategyConfig.model_validate(data)
    except Exception as exc:
        raise StrategyLoadError(f"Invalid strategy configuration in {path}: {exc}") from exc
