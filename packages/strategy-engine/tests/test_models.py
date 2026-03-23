"""Tests for S2-E01: strategy engine models and YAML loading."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pnlclaw_strategy.models import (
    ConditionRule,
    EngineStrategyConfig,
    EntryRules,
    RiskParams,
    StrategyLoadError,
    load_strategy,
)
from pnlclaw_types.strategy import StrategyConfig

SAMPLE_YAML = """\
id: strat-001
name: BTC SMA Cross
type: sma_cross
description: Simple SMA crossover
symbols:
  - BTC/USDT
interval: 1h
parameters:
  sma_short: 20
  sma_long: 50
entry_rules:
  long:
    - indicator: sma
      params: {period: 20}
      operator: crosses_above
      comparator:
        indicator: sma
        params: {period: 50}
exit_rules:
  close_long:
    - indicator: sma
      params: {period: 20}
      operator: crosses_below
      comparator:
        indicator: sma
        params: {period: 50}
risk_params:
  stop_loss_pct: 0.02
  take_profit_pct: 0.05
  max_position_pct: 0.1
"""


class TestEngineStrategyConfig:
    """Test EngineStrategyConfig model."""

    def test_inherits_strategy_config(self) -> None:
        assert issubclass(EngineStrategyConfig, StrategyConfig)

    def test_create_minimal(self) -> None:
        config = EngineStrategyConfig(
            id="s1",
            name="Test",
            type="sma_cross",
            symbols=["BTC/USDT"],
            interval="1h",
        )
        assert config.id == "s1"
        assert config.parsed_entry_rules.long == []
        assert config.parsed_risk_params.max_position_pct == 0.1

    def test_create_with_rules(self) -> None:
        rule = ConditionRule(
            indicator="sma",
            params={"period": 20},
            operator="crosses_above",
            comparator={"indicator": "sma", "params": {"period": 50}},
        )
        config = EngineStrategyConfig(
            id="s1",
            name="Test",
            type="sma_cross",
            symbols=["BTC/USDT"],
            interval="1h",
            parsed_entry_rules=EntryRules(long=[rule]),
            parsed_risk_params=RiskParams(stop_loss_pct=0.02),
        )
        assert len(config.parsed_entry_rules.long) == 1
        assert config.parsed_risk_params.stop_loss_pct == 0.02


class TestConditionRule:
    """Test ConditionRule model."""

    def test_with_numeric_comparator(self) -> None:
        rule = ConditionRule(
            indicator="rsi", params={"period": 14}, operator="less_than", comparator=30.0
        )
        assert rule.comparator == 30.0

    def test_with_indicator_comparator(self) -> None:
        rule = ConditionRule(
            indicator="sma",
            params={"period": 20},
            operator="crosses_above",
            comparator={"indicator": "sma", "params": {"period": 50}},
        )
        assert isinstance(rule.comparator, dict)


class TestRiskParams:
    """Test RiskParams model."""

    def test_defaults(self) -> None:
        rp = RiskParams()
        assert rp.stop_loss_pct is None
        assert rp.max_position_pct == 0.1
        assert rp.max_open_positions == 1

    def test_validation_bounds(self) -> None:
        with pytest.raises(ValidationError):
            RiskParams(stop_loss_pct=1.5)


class TestLoadStrategy:
    """Test YAML strategy loading."""

    def test_load_valid_yaml(self, tmp_yaml) -> None:
        path = tmp_yaml(SAMPLE_YAML)
        config = load_strategy(path)
        assert config.id == "strat-001"
        assert config.name == "BTC SMA Cross"
        assert len(config.parsed_entry_rules.long) == 1
        assert config.parsed_risk_params.stop_loss_pct == 0.02

    def test_load_missing_file(self) -> None:
        with pytest.raises(StrategyLoadError, match="not found"):
            load_strategy("/nonexistent/path.yaml")

    def test_load_wrong_extension(self, tmp_path) -> None:
        p = tmp_path / "strategy.txt"
        p.write_text("id: s1")
        with pytest.raises(StrategyLoadError, match="Expected .yaml"):
            load_strategy(p)

    def test_load_invalid_yaml(self, tmp_yaml) -> None:
        path = tmp_yaml("{{invalid yaml::")
        with pytest.raises(StrategyLoadError, match="Invalid YAML"):
            load_strategy(path)

    def test_load_non_mapping(self, tmp_yaml) -> None:
        path = tmp_yaml("- item1\n- item2\n")
        with pytest.raises(StrategyLoadError, match="Expected a YAML mapping"):
            load_strategy(path)

    def test_load_missing_required_fields(self, tmp_yaml) -> None:
        path = tmp_yaml("id: s1\nname: Test\n")
        with pytest.raises(StrategyLoadError, match="Invalid strategy"):
            load_strategy(path)

    def test_json_serialization_roundtrip(self, tmp_yaml) -> None:
        path = tmp_yaml(SAMPLE_YAML)
        config = load_strategy(path)
        json_str = config.model_dump_json()
        restored = EngineStrategyConfig.model_validate_json(json_str)
        assert restored.id == config.id
        assert len(restored.parsed_entry_rules.long) == len(config.parsed_entry_rules.long)
