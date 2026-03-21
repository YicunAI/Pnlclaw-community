"""Tests for S2-E09: strategy lifecycle management."""

from __future__ import annotations

import pytest

from pnlclaw_strategy.lifecycle import (
    BacktestReadyStrategy,
    LifecycleError,
    StrategyDraft,
    StrategyState,
    ValidatedStrategy,
    draft_from_config,
    submit_for_backtest,
    validate_draft,
)
from pnlclaw_strategy.models import (
    ConditionRule,
    EngineStrategyConfig,
    EntryRules,
    ExitRules,
)


def _valid_config() -> EngineStrategyConfig:
    """Create a valid strategy config."""
    return EngineStrategyConfig(
        id="lifecycle-test",
        name="Lifecycle Test",
        type="sma_cross",
        symbols=["BTC/USDT"],
        interval="1h",
        parsed_entry_rules=EntryRules(
            long=[
                ConditionRule(
                    indicator="sma",
                    params={"period": 20},
                    operator="crosses_above",
                    comparator={"indicator": "sma", "params": {"period": 50}},
                )
            ]
        ),
        parsed_exit_rules=ExitRules(
            close_long=[
                ConditionRule(
                    indicator="sma",
                    params={"period": 20},
                    operator="crosses_below",
                    comparator={"indicator": "sma", "params": {"period": 50}},
                )
            ]
        ),
    )


def _invalid_config() -> EngineStrategyConfig:
    """Create a config with invalid indicator reference."""
    return EngineStrategyConfig(
        id="bad",
        name="Bad",
        type="custom",
        symbols=["BTC/USDT"],
        interval="1h",
        parsed_entry_rules=EntryRules(
            long=[
                ConditionRule(
                    indicator="nonexistent",
                    params={"period": 14},
                    operator="crosses_above",
                    comparator=50.0,
                )
            ]
        ),
        parsed_exit_rules=ExitRules(
            close_long=[
                ConditionRule(
                    indicator="nonexistent",
                    params={"period": 14},
                    operator="crosses_below",
                    comparator=50.0,
                )
            ]
        ),
    )


class TestStrategyState:
    """Test StrategyState enum."""

    def test_all_states_exist(self) -> None:
        assert StrategyState.DRAFT == "draft"
        assert StrategyState.VALIDATED == "validated"
        assert StrategyState.BACKTESTING == "backtesting"
        assert StrategyState.CONFIRMED == "confirmed"
        assert StrategyState.RUNNING == "running"
        assert StrategyState.RETIRED == "retired"


class TestDraftFromConfig:
    """Test draft creation."""

    def test_creates_draft(self) -> None:
        config = _valid_config()
        draft = draft_from_config(config)
        assert isinstance(draft, StrategyDraft)
        assert draft.state == StrategyState.DRAFT
        assert draft.config is config
        assert draft.created_at is not None

    def test_with_metadata(self) -> None:
        config = _valid_config()
        draft = draft_from_config(config, metadata={"source": "ai"})
        assert draft.metadata == {"source": "ai"}

    def test_default_metadata_empty(self) -> None:
        config = _valid_config()
        draft = draft_from_config(config)
        assert draft.metadata == {}


class TestValidateDraft:
    """Test draft validation."""

    def test_valid_draft_transitions(self) -> None:
        config = _valid_config()
        draft = draft_from_config(config)
        validated = validate_draft(draft)
        assert isinstance(validated, ValidatedStrategy)
        assert validated.state == StrategyState.VALIDATED
        assert validated.validation_result.valid

    def test_invalid_config_raises(self) -> None:
        config = _invalid_config()
        draft = draft_from_config(config)
        with pytest.raises(LifecycleError, match="validation failed"):
            validate_draft(draft)

    def test_wrong_state_raises(self) -> None:
        config = _valid_config()
        draft = draft_from_config(config)
        # Manually change state
        draft.state = StrategyState.VALIDATED
        with pytest.raises(LifecycleError, match="expected 'draft'"):
            validate_draft(draft)

    def test_empty_rules_valid(self) -> None:
        config = EngineStrategyConfig(
            id="empty",
            name="Empty",
            type="custom",
            symbols=["BTC/USDT"],
            interval="1h",
        )
        draft = draft_from_config(config)
        validated = validate_draft(draft)
        assert validated.state == StrategyState.VALIDATED


class TestSubmitForBacktest:
    """Test backtest submission."""

    def test_submit_valid_strategy(self) -> None:
        config = _valid_config()
        draft = draft_from_config(config)
        validated = validate_draft(draft)
        ready = submit_for_backtest(validated)
        assert isinstance(ready, BacktestReadyStrategy)
        assert ready.state == StrategyState.BACKTESTING
        assert ready.compiled is not None
        assert ready.submitted_at is not None

    def test_wrong_state_raises(self) -> None:
        config = _valid_config()
        draft = draft_from_config(config)
        validated = validate_draft(draft)
        # Manually change state
        validated.state = StrategyState.DRAFT
        with pytest.raises(LifecycleError, match="expected 'validated'"):
            submit_for_backtest(validated)

    def test_compiled_strategy_has_indicators(self) -> None:
        config = _valid_config()
        draft = draft_from_config(config)
        validated = validate_draft(draft)
        ready = submit_for_backtest(validated)
        assert len(ready.compiled.indicators) > 0
        assert len(ready.compiled.long_entry_conditions) > 0


class TestFullLifecycle:
    """Test the complete v0.1 lifecycle: draft → validate → backtest."""

    def test_full_flow(self) -> None:
        config = _valid_config()

        # Step 1: Draft
        draft = draft_from_config(config, metadata={"source": "test"})
        assert draft.state == StrategyState.DRAFT

        # Step 2: Validate
        validated = validate_draft(draft)
        assert validated.state == StrategyState.VALIDATED

        # Step 3: Submit for backtest
        ready = submit_for_backtest(validated)
        assert ready.state == StrategyState.BACKTESTING
        assert ready.compiled.config.id == config.id
