"""Tests for S2-E02: strategy validator."""

from __future__ import annotations

import pytest

from pnlclaw_strategy.models import (
    ConditionRule,
    EngineStrategyConfig,
    EntryRules,
    ExitRules,
    RiskParams,
)
from pnlclaw_strategy.validator import ValidationResult, validate


def _make_config(**overrides) -> EngineStrategyConfig:
    """Helper to create a config with sensible defaults."""
    defaults = dict(
        id="test",
        name="Test Strategy",
        type="sma_cross",
        symbols=["BTC/USDT"],
        interval="1h",
        parameters={},
    )
    defaults.update(overrides)
    return EngineStrategyConfig(**defaults)


def _make_rule(
    indicator: str = "sma",
    params: dict | None = None,
    operator: str = "crosses_above",
    comparator: dict | float = 50.0,
) -> ConditionRule:
    return ConditionRule(
        indicator=indicator,
        params=params or {"period": 20},
        operator=operator,
        comparator=comparator,
    )


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_default_valid(self) -> None:
        r = ValidationResult()
        assert r.valid is True
        assert r.errors == []

    def test_add_error(self) -> None:
        r = ValidationResult()
        r.add_error("something wrong")
        assert r.valid is False
        assert "something wrong" in r.errors


class TestParameterRangeValidation:
    """Test parameter range checks."""

    def test_valid_parameters(self) -> None:
        config = _make_config(parameters={"period": 14})
        result = validate(config)
        assert result.valid

    def test_negative_period(self) -> None:
        config = _make_config(parameters={"period": -5})
        result = validate(config)
        assert not result.valid
        assert any("period" in e and "positive" in e for e in result.errors)

    def test_zero_period(self) -> None:
        config = _make_config(parameters={"period": 0})
        result = validate(config)
        assert not result.valid

    def test_float_period(self) -> None:
        config = _make_config(parameters={"period": 14.5})
        result = validate(config)
        assert not result.valid
        assert any("integer" in e for e in result.errors)

    def test_rule_params_validated(self) -> None:
        bad_rule = _make_rule(params={"period": -1})
        config = _make_config(
            parsed_entry_rules=EntryRules(long=[bad_rule]),
            parsed_exit_rules=ExitRules(close_long=[_make_rule(operator="crosses_below")]),
        )
        result = validate(config)
        assert not result.valid
        assert any("entry_rules" in e for e in result.errors)


class TestLogicConsistencyValidation:
    """Test logic consistency checks."""

    def test_long_entry_without_exit(self) -> None:
        config = _make_config(
            parsed_entry_rules=EntryRules(long=[_make_rule()]),
            parsed_exit_rules=ExitRules(),
        )
        result = validate(config)
        assert not result.valid
        assert any("close_long" in e for e in result.errors)

    def test_short_entry_without_exit(self) -> None:
        config = _make_config(
            parsed_entry_rules=EntryRules(short=[_make_rule()]),
            parsed_exit_rules=ExitRules(),
        )
        result = validate(config)
        assert not result.valid
        assert any("close_short" in e for e in result.errors)

    def test_matching_entry_exit_ok(self) -> None:
        entry_rule = _make_rule(operator="crosses_above")
        exit_rule = _make_rule(operator="crosses_below")
        config = _make_config(
            parsed_entry_rules=EntryRules(long=[entry_rule]),
            parsed_exit_rules=ExitRules(close_long=[exit_rule]),
        )
        result = validate(config)
        assert result.valid

    def test_identical_entry_exit_rejected(self) -> None:
        rule = _make_rule(operator="crosses_above")
        config = _make_config(
            parsed_entry_rules=EntryRules(long=[rule]),
            parsed_exit_rules=ExitRules(close_long=[rule]),
        )
        result = validate(config)
        assert not result.valid
        assert any("identical" in e for e in result.errors)


class TestDataAvailabilityValidation:
    """Test indicator data availability checks."""

    def test_known_indicator_passes(self) -> None:
        rule = _make_rule(indicator="sma")
        config = _make_config(
            parsed_entry_rules=EntryRules(long=[rule]),
            parsed_exit_rules=ExitRules(close_long=[_make_rule(indicator="sma", operator="crosses_below")]),
        )
        result = validate(config)
        assert result.valid

    def test_unknown_indicator_fails(self) -> None:
        rule = _make_rule(indicator="ichimoku")
        config = _make_config(
            parsed_entry_rules=EntryRules(long=[rule]),
            parsed_exit_rules=ExitRules(close_long=[_make_rule(indicator="ichimoku", operator="crosses_below")]),
        )
        result = validate(config)
        assert not result.valid
        assert any("ichimoku" in e for e in result.errors)

    def test_custom_available_indicators(self) -> None:
        rule = _make_rule(indicator="custom_ind")
        config = _make_config(
            parsed_entry_rules=EntryRules(long=[rule]),
            parsed_exit_rules=ExitRules(close_long=[_make_rule(indicator="custom_ind", operator="crosses_below")]),
        )
        result = validate(config, available_indicators={"custom_ind"})
        assert result.valid

    def test_comparator_indicator_checked(self) -> None:
        rule = _make_rule(
            indicator="sma",
            comparator={"indicator": "unknown_ind", "params": {"period": 50}},
        )
        config = _make_config(
            parsed_entry_rules=EntryRules(long=[rule]),
            parsed_exit_rules=ExitRules(close_long=[_make_rule(operator="crosses_below")]),
        )
        result = validate(config)
        assert not result.valid
        assert any("unknown_ind" in e for e in result.errors)


class TestValidateEmptyStrategy:
    """Test validation of minimal strategies."""

    def test_no_rules_is_valid(self) -> None:
        config = _make_config()
        result = validate(config)
        assert result.valid
