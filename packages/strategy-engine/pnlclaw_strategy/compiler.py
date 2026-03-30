"""Strategy compiler — transforms StrategyConfig into an executable StrategyRuntime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pnlclaw_strategy.indicators.registry import (
    IndicatorNotFoundError,
    IndicatorRegistry,
    indicator_registry,
)
from pnlclaw_strategy.models import ConditionRule, EngineStrategyConfig
from pnlclaw_strategy.validator import validate

if TYPE_CHECKING:
    from pnlclaw_strategy.indicators.base import Indicator


# ---------------------------------------------------------------------------
# Compilation errors
# ---------------------------------------------------------------------------


class CompilationError(Exception):
    """Raised when a strategy cannot be compiled."""


# ---------------------------------------------------------------------------
# Compiled rule — an executable condition
# ---------------------------------------------------------------------------


@dataclass
class CompiledCondition:
    """A single compiled condition ready for evaluation.

    Attributes:
        indicator: Instantiated indicator for the left-hand side.
        operator: Comparison operator string.
        comparator_indicator: Instantiated indicator for the right-hand side
            (None if comparing against a fixed value).
        comparator_value: Fixed numeric value to compare against
            (None if comparing against another indicator).
        column_name: Unique column name for this indicator's output in the DataFrame.
        comparator_column_name: Unique column name for the comparator indicator's output.
    """

    indicator: Indicator
    operator: str
    comparator_indicator: Indicator | None = None
    comparator_value: float | None = None
    column_name: str = ""
    comparator_column_name: str = ""


@dataclass
class CompiledStrategy:
    """Compiled strategy ready to be passed to StrategyRuntime.

    Contains all instantiated indicators and compiled conditions.
    """

    config: EngineStrategyConfig
    indicators: dict[str, Indicator] = field(default_factory=dict)
    long_entry_conditions: list[CompiledCondition] = field(default_factory=list)
    short_entry_conditions: list[CompiledCondition] = field(default_factory=list)
    close_long_conditions: list[CompiledCondition] = field(default_factory=list)
    close_short_conditions: list[CompiledCondition] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------


def _make_column_name(indicator_name: str, params: dict) -> str:
    """Generate a unique column name for an indicator's output."""
    parts = [indicator_name]
    for k, v in sorted(params.items()):
        parts.append(f"{k}={v}")
    return "_".join(parts)


def _resolve_indicator(
    name: str,
    params: dict,
    registry: IndicatorRegistry,
    cache: dict[str, Indicator],
) -> tuple[Indicator, str]:
    """Resolve an indicator reference into an instance.

    Returns (indicator_instance, column_name). Uses cache to share
    indicator instances when the same indicator+params combo appears
    multiple times.

    For ``macd_signal`` and ``macd_histogram``, the underlying MACD
    indicator is resolved and the appropriate sub-column name is returned.
    """
    # Map macd_signal / macd_histogram to the base macd indicator
    macd_sub: str | None = None
    resolved_name = name
    if name in ("macd_signal", "macd_histogram"):
        macd_sub = name  # remember which sub-column
        resolved_name = "macd"
    elif name in ("bbands_upper", "bbands_lower", "bbands_middle"):
        macd_sub = name
        resolved_name = "bbands"

    col_name = _make_column_name(resolved_name, params)

    # For MACD sub-columns, derive the appropriate column name
    if macd_sub is not None:
        col_name = col_name.replace("macd", macd_sub, 1)

    if col_name in cache:
        return cache[col_name], col_name

    try:
        cls = registry.get(resolved_name)
    except IndicatorNotFoundError as exc:
        raise CompilationError(str(exc)) from exc

    # Build kwargs for the indicator constructor
    kwargs = {}
    if "period" in params:
        kwargs["period"] = int(params["period"])

    # MACD-specific params
    if resolved_name == "macd":
        if "fast_period" in params:
            kwargs["fast_period"] = int(params["fast_period"])
        if "slow_period" in params:
            kwargs["period"] = int(params["slow_period"])
        if "signal_period" in params:
            kwargs["signal_period"] = int(params["signal_period"])

    try:
        instance = cls(**kwargs) if kwargs else cls(period=14)
    except (TypeError, ValueError) as exc:
        raise CompilationError(
            f"Cannot instantiate indicator '{name}' with params {params}: {exc}"
        ) from exc

    cache[col_name] = instance

    # For MACD (whether base or sub-column), register all three columns
    if resolved_name == "macd":
        base_col = _make_column_name("macd", params)
        signal_col = base_col.replace("macd", "macd_signal", 1)
        hist_col = base_col.replace("macd", "macd_histogram", 1)
        cache.setdefault(base_col, instance)
        cache.setdefault(signal_col, instance)
        cache.setdefault(hist_col, instance)

    # For Bollinger Bands, register upper/middle/lower columns
    if resolved_name == "bbands":
        base_col = _make_column_name("bbands", params)
        upper_col = base_col.replace("bbands", "bbands_upper", 1)
        middle_col = base_col.replace("bbands", "bbands_middle", 1)
        lower_col = base_col.replace("bbands", "bbands_lower", 1)
        cache.setdefault(base_col, instance)
        cache.setdefault(upper_col, instance)
        cache.setdefault(middle_col, instance)
        cache.setdefault(lower_col, instance)

    return instance, col_name


def _compile_condition(
    rule: ConditionRule,
    registry: IndicatorRegistry,
    indicator_cache: dict[str, Indicator],
) -> CompiledCondition:
    """Compile a single ConditionRule into a CompiledCondition."""
    ind, col_name = _resolve_indicator(rule.indicator, rule.params, registry, indicator_cache)

    comp_ind = None
    comp_val = None
    comp_col = ""

    if isinstance(rule.comparator, (int, float)):
        comp_val = float(rule.comparator)
    elif isinstance(rule.comparator, dict):
        comp_name = rule.comparator.get("indicator", "")
        comp_params = rule.comparator.get("params", {})
        if comp_name:
            comp_ind, comp_col = _resolve_indicator(
                comp_name, comp_params, registry, indicator_cache
            )
        else:
            raise CompilationError(f"Comparator dict must have 'indicator' key: {rule.comparator}")
    else:
        raise CompilationError(f"Invalid comparator type: {type(rule.comparator)}")

    return CompiledCondition(
        indicator=ind,
        operator=rule.operator,
        comparator_indicator=comp_ind,
        comparator_value=comp_val,
        column_name=col_name,
        comparator_column_name=comp_col,
    )


def compile(
    config: EngineStrategyConfig,
    registry: IndicatorRegistry | None = None,
) -> CompiledStrategy:
    """Compile a strategy configuration into an executable CompiledStrategy.

    Steps:
    1. Validate the config (parameters, logic, data availability).
    2. Resolve all indicator references from the registry.
    3. Compile entry/exit conditions into CompiledCondition objects.

    Args:
        config: The strategy configuration to compile.
        registry: Indicator registry to use. Defaults to the global registry.

    Returns:
        CompiledStrategy ready for the runtime.

    Raises:
        CompilationError: If validation fails or indicators cannot be resolved.
    """
    if registry is None:
        registry = indicator_registry

    # Validate first
    available = set(registry.list())
    validation = validate(config, available_indicators=available)
    if not validation.valid:
        raise CompilationError(f"Strategy validation failed: {'; '.join(validation.errors)}")

    indicator_cache: dict[str, Indicator] = {}
    compiled = CompiledStrategy(config=config)

    # Compile entry conditions
    for rule in config.parsed_entry_rules.long:
        condition = _compile_condition(rule, registry, indicator_cache)
        compiled.long_entry_conditions.append(condition)

    for rule in config.parsed_entry_rules.short:
        condition = _compile_condition(rule, registry, indicator_cache)
        compiled.short_entry_conditions.append(condition)

    # Compile exit conditions
    for rule in config.parsed_exit_rules.close_long:
        condition = _compile_condition(rule, registry, indicator_cache)
        compiled.close_long_conditions.append(condition)

    for rule in config.parsed_exit_rules.close_short:
        condition = _compile_condition(rule, registry, indicator_cache)
        compiled.close_short_conditions.append(condition)

    # Collect all unique indicators
    compiled.indicators = indicator_cache

    return compiled
