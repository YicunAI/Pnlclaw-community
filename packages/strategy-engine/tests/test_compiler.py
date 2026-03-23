"""Tests for S2-E06: strategy compiler."""

from __future__ import annotations

import pytest

from pnlclaw_strategy.compiler import (
    CompilationError,
    CompiledStrategy,
    compile,
)
from pnlclaw_strategy.models import (
    ConditionRule,
    EngineStrategyConfig,
    EntryRules,
    ExitRules,
    RiskParams,
)


def _sma_cross_config() -> EngineStrategyConfig:
    """Create a typical SMA cross strategy config."""
    entry_rule = ConditionRule(
        indicator="sma",
        params={"period": 20},
        operator="crosses_above",
        comparator={"indicator": "sma", "params": {"period": 50}},
    )
    exit_rule = ConditionRule(
        indicator="sma",
        params={"period": 20},
        operator="crosses_below",
        comparator={"indicator": "sma", "params": {"period": 50}},
    )
    return EngineStrategyConfig(
        id="sma-cross",
        name="SMA Cross",
        type="sma_cross",
        symbols=["BTC/USDT"],
        interval="1h",
        parsed_entry_rules=EntryRules(long=[entry_rule]),
        parsed_exit_rules=ExitRules(close_long=[exit_rule]),
        parsed_risk_params=RiskParams(stop_loss_pct=0.02),
    )


class TestCompile:
    """Test strategy compilation."""

    def test_compile_sma_cross(self) -> None:
        config = _sma_cross_config()
        compiled = compile(config)

        assert isinstance(compiled, CompiledStrategy)
        assert compiled.config is config
        assert len(compiled.long_entry_conditions) == 1
        assert len(compiled.close_long_conditions) == 1
        assert len(compiled.short_entry_conditions) == 0
        assert len(compiled.close_short_conditions) == 0

    def test_compiled_indicators_cached(self) -> None:
        config = _sma_cross_config()
        compiled = compile(config)

        # SMA(20) and SMA(50) should both be in the indicator cache
        assert len(compiled.indicators) == 2
        names = {ind.name for ind in compiled.indicators.values()}
        assert names == {"sma"}

    def test_compiled_condition_structure(self) -> None:
        config = _sma_cross_config()
        compiled = compile(config)

        cond = compiled.long_entry_conditions[0]
        assert cond.indicator.name == "sma"
        assert cond.indicator.period == 20
        assert cond.operator == "crosses_above"
        assert cond.comparator_indicator is not None
        assert cond.comparator_indicator.name == "sma"
        assert cond.comparator_indicator.period == 50

    def test_compile_rsi_with_numeric_comparator(self) -> None:
        entry_rule = ConditionRule(
            indicator="rsi",
            params={"period": 14},
            operator="less_than",
            comparator=30.0,
        )
        exit_rule = ConditionRule(
            indicator="rsi",
            params={"period": 14},
            operator="greater_than",
            comparator=70.0,
        )
        config = EngineStrategyConfig(
            id="rsi-test",
            name="RSI Test",
            type="rsi_reversal",
            symbols=["BTC/USDT"],
            interval="1h",
            parsed_entry_rules=EntryRules(long=[entry_rule]),
            parsed_exit_rules=ExitRules(close_long=[exit_rule]),
        )
        compiled = compile(config)
        cond = compiled.long_entry_conditions[0]
        assert cond.comparator_value == 30.0
        assert cond.comparator_indicator is None

    def test_compile_empty_rules(self) -> None:
        config = EngineStrategyConfig(
            id="empty",
            name="Empty Strategy",
            type="custom",
            symbols=["BTC/USDT"],
            interval="1h",
        )
        compiled = compile(config)
        assert len(compiled.indicators) == 0
        assert len(compiled.long_entry_conditions) == 0

    def test_compile_unknown_indicator_fails(self) -> None:
        entry_rule = ConditionRule(
            indicator="ichimoku",
            params={"period": 9},
            operator="crosses_above",
            comparator=50.0,
        )
        config = EngineStrategyConfig(
            id="bad",
            name="Bad Strategy",
            type="custom",
            symbols=["BTC/USDT"],
            interval="1h",
            parsed_entry_rules=EntryRules(long=[entry_rule]),
            parsed_exit_rules=ExitRules(
                close_long=[
                    ConditionRule(
                        indicator="ichimoku",
                        params={"period": 9},
                        operator="crosses_below",
                        comparator=50.0,
                    )
                ]
            ),
        )
        with pytest.raises(CompilationError, match="ichimoku"):
            compile(config)

    def test_compile_invalid_params_fails(self) -> None:
        entry_rule = ConditionRule(
            indicator="sma",
            params={"period": -5},
            operator="crosses_above",
            comparator=50.0,
        )
        config = EngineStrategyConfig(
            id="bad",
            name="Bad Params",
            type="custom",
            symbols=["BTC/USDT"],
            interval="1h",
            parsed_entry_rules=EntryRules(long=[entry_rule]),
            parsed_exit_rules=ExitRules(
                close_long=[
                    ConditionRule(
                        indicator="sma",
                        params={"period": -5},
                        operator="crosses_below",
                        comparator=50.0,
                    )
                ]
            ),
        )
        with pytest.raises(CompilationError):
            compile(config)

    def test_indicator_sharing_between_entry_exit(self) -> None:
        """Same indicator+params in entry and exit should share instance."""
        rule = ConditionRule(
            indicator="sma",
            params={"period": 20},
            operator="crosses_above",
            comparator={"indicator": "sma", "params": {"period": 50}},
        )
        exit_rule = ConditionRule(
            indicator="sma",
            params={"period": 20},
            operator="crosses_below",
            comparator={"indicator": "sma", "params": {"period": 50}},
        )
        config = EngineStrategyConfig(
            id="shared",
            name="Shared Indicators",
            type="sma_cross",
            symbols=["BTC/USDT"],
            interval="1h",
            parsed_entry_rules=EntryRules(long=[rule]),
            parsed_exit_rules=ExitRules(close_long=[exit_rule]),
        )
        compiled = compile(config)
        # Should be exactly 2 unique indicators (SMA(20) and SMA(50))
        assert len(compiled.indicators) == 2
