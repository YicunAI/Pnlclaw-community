"""Strategy validator — validates StrategyConfig for correctness before compilation.

Three validation categories:
1. Parameter range — numeric params within valid bounds (e.g. RSI period > 0)
2. Logic consistency — entry/exit rules are not contradictory
3. Data availability — referenced indicators exist in the registry
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pnlclaw_strategy.models import EngineStrategyConfig


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Result of strategy validation.

    Attributes:
        valid: True if the strategy passed all checks.
        errors: List of human-readable error descriptions.
    """

    valid: bool = True
    errors: list[str] = field(default_factory=list)

    def add_error(self, message: str) -> None:
        """Record a validation error and mark result as invalid."""
        self.valid = False
        self.errors.append(message)


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

# Common indicator parameter constraints: {param_name: (min_exclusive, description)}
_PERIOD_INDICATORS = {"sma", "ema", "rsi"}
_POSITIVE_INT_PARAMS = {"period", "fast_period", "slow_period", "signal_period"}


def _validate_parameter_ranges(config: EngineStrategyConfig, result: ValidationResult) -> None:
    """Check that strategy parameters are within valid ranges."""
    params = config.parameters

    for key, value in params.items():
        if key in _POSITIVE_INT_PARAMS:
            if not isinstance(value, (int, float)) or value <= 0:
                result.add_error(f"Parameter '{key}' must be a positive number, got {value!r}")
            elif isinstance(value, float) and not value.is_integer():
                result.add_error(f"Parameter '{key}' must be an integer, got {value}")

    # Validate indicator params inside rules
    for section_name, rules_obj in [
        ("entry_rules", config.parsed_entry_rules),
        ("exit_rules", config.parsed_exit_rules),
    ]:
        for direction in ("long", "short", "close_long", "close_short"):
            rules = getattr(rules_obj, direction, [])
            for i, rule in enumerate(rules):
                for pname, pval in rule.params.items():
                    if pname in _POSITIVE_INT_PARAMS:
                        if not isinstance(pval, (int, float)) or pval <= 0:
                            result.add_error(
                                f"{section_name}.{direction}[{i}]: "
                                f"parameter '{pname}' must be positive, got {pval!r}"
                            )

                # Validate comparator params if it's an indicator reference
                if isinstance(rule.comparator, dict) and "params" in rule.comparator:
                    for pname, pval in rule.comparator["params"].items():
                        if pname in _POSITIVE_INT_PARAMS:
                            if not isinstance(pval, (int, float)) or pval <= 0:
                                result.add_error(
                                    f"{section_name}.{direction}[{i}].comparator: "
                                    f"parameter '{pname}' must be positive, got {pval!r}"
                                )


def _validate_logic_consistency(config: EngineStrategyConfig, result: ValidationResult) -> None:
    """Check for logical contradictions in entry/exit rules."""
    entry = config.parsed_entry_rules
    exit_ = config.parsed_exit_rules

    # Check: if there are long entry rules, there should be close_long exit rules
    if entry.long and not exit_.close_long:
        result.add_error("Strategy has long entry rules but no close_long exit rules")

    # Check: if there are short entry rules, there should be close_short exit rules
    if entry.short and not exit_.close_short:
        result.add_error("Strategy has short entry rules but no close_short exit rules")

    # Check: entry and exit should not be identical (would cause instant close)
    if entry.long and exit_.close_long:
        entry_sigs = {(r.indicator, r.operator, str(r.params)) for r in entry.long}
        exit_sigs = {(r.indicator, r.operator, str(r.params)) for r in exit_.close_long}
        if entry_sigs == exit_sigs:
            result.add_error(
                "Long entry and close_long exit conditions are identical — "
                "positions would close immediately"
            )

    if entry.short and exit_.close_short:
        entry_sigs = {(r.indicator, r.operator, str(r.params)) for r in entry.short}
        exit_sigs = {(r.indicator, r.operator, str(r.params)) for r in exit_.close_short}
        if entry_sigs == exit_sigs:
            result.add_error(
                "Short entry and close_short exit conditions are identical — "
                "positions would close immediately"
            )


def _validate_data_availability(
    config: EngineStrategyConfig,
    result: ValidationResult,
    available_indicators: set[str] | None = None,
) -> None:
    """Check that all referenced indicators are available."""
    if available_indicators is None:
        # Default to built-in indicators
        available_indicators = {"sma", "ema", "rsi", "macd"}

    # Collect all indicator references from rules
    referenced: list[tuple[str, str]] = []  # (location, indicator_name)

    for section_name, rules_obj in [
        ("entry_rules", config.parsed_entry_rules),
        ("exit_rules", config.parsed_exit_rules),
    ]:
        for direction in ("long", "short", "close_long", "close_short"):
            rules = getattr(rules_obj, direction, [])
            for i, rule in enumerate(rules):
                loc = f"{section_name}.{direction}[{i}]"
                referenced.append((loc, rule.indicator))
                if isinstance(rule.comparator, dict) and "indicator" in rule.comparator:
                    referenced.append((f"{loc}.comparator", rule.comparator["indicator"]))

    for loc, name in referenced:
        if name not in available_indicators:
            available = sorted(available_indicators)
            result.add_error(
                f"{loc}: unknown indicator '{name}' (available: {available})"
            )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate(
    config: EngineStrategyConfig,
    available_indicators: set[str] | None = None,
) -> ValidationResult:
    """Validate a strategy configuration.

    Runs three validation passes:
    1. Parameter ranges — numeric values within valid bounds
    2. Logic consistency — entry/exit rules not contradictory
    3. Data availability — referenced indicators exist

    Args:
        config: The strategy configuration to validate.
        available_indicators: Set of known indicator names. If None, uses
            the default built-in set: {sma, ema, rsi, macd}.

    Returns:
        ValidationResult with valid=True if all checks pass, or
        valid=False with a list of error descriptions.
    """
    result = ValidationResult()

    # Basic sanity checks
    if not config.symbols:
        result.add_error("Strategy must specify at least one symbol")
    if not config.interval:
        result.add_error("Strategy must specify an interval")

    _validate_parameter_ranges(config, result)
    _validate_logic_consistency(config, result)
    _validate_data_availability(config, result, available_indicators)

    return result
