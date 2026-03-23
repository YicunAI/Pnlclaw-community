"""Strategy lifecycle management — tracks strategy state through draft → validate → backtest.

v0.1 implements the first 3 stages. Full lifecycle (deploy/monitor/retire)
is deferred to later versions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pnlclaw_strategy.compiler import CompilationError, CompiledStrategy, compile
from pnlclaw_strategy.models import EngineStrategyConfig
from pnlclaw_strategy.validator import ValidationResult, validate

# ---------------------------------------------------------------------------
# Strategy state enum
# ---------------------------------------------------------------------------


class StrategyState(str, Enum):
    """Strategy lifecycle states.

    v0.1 flow: DRAFT → VALIDATED → BACKTESTING
    Future: → CONFIRMED → RUNNING → RETIRED
    """

    DRAFT = "draft"
    VALIDATED = "validated"
    BACKTESTING = "backtesting"
    # v0.2+ states
    CONFIRMED = "confirmed"
    RUNNING = "running"
    RETIRED = "retired"


# ---------------------------------------------------------------------------
# Lifecycle errors
# ---------------------------------------------------------------------------


class LifecycleError(Exception):
    """Raised when a lifecycle transition is invalid."""


# ---------------------------------------------------------------------------
# Lifecycle wrapper models
# ---------------------------------------------------------------------------


class StrategyDraft(BaseModel):
    """A strategy in DRAFT state — freshly created, not yet validated.

    Wraps EngineStrategyConfig with lifecycle metadata.
    """

    config: EngineStrategyConfig = Field(..., description="The strategy configuration")
    state: StrategyState = Field(StrategyState.DRAFT, description="Current lifecycle state")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the draft was created",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary metadata (source, author, etc.)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "config": {
                        "id": "strat-001",
                        "name": "BTC SMA Cross",
                        "type": "sma_cross",
                        "symbols": ["BTC/USDT"],
                        "interval": "1h",
                    },
                    "state": "draft",
                    "created_at": "2026-03-22T00:00:00Z",
                    "metadata": {"source": "user"},
                }
            ]
        }
    )


class ValidatedStrategy(BaseModel):
    """A strategy that has passed validation — ready for backtesting.

    Contains the original config, validation result, and compiled strategy.
    """

    config: EngineStrategyConfig = Field(..., description="The strategy configuration")
    state: StrategyState = Field(StrategyState.VALIDATED, description="Current lifecycle state")
    validation_result: ValidationResult = Field(
        ..., description="Validation result (should be valid)"
    )
    validated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When validation passed",
    )

    model_config = ConfigDict(arbitrary_types_allowed=True)


class BacktestReadyStrategy:
    """A validated strategy submitted for backtesting.

    Uses a plain class (not Pydantic) because it wraps CompiledStrategy
    which contains non-serializable Indicator instances.

    Attributes:
        config: The strategy configuration.
        state: Current lifecycle state (BACKTESTING).
        compiled: Compiled strategy for the backtest engine.
        submitted_at: When the strategy was submitted for backtesting.
    """

    __slots__ = ("config", "state", "compiled", "submitted_at")

    def __init__(
        self,
        config: EngineStrategyConfig,
        compiled: CompiledStrategy,
        state: StrategyState = StrategyState.BACKTESTING,
        submitted_at: datetime | None = None,
    ) -> None:
        self.config = config
        self.state = state
        self.compiled = compiled
        self.submitted_at = submitted_at or datetime.now(UTC)


# ---------------------------------------------------------------------------
# Lifecycle functions
# ---------------------------------------------------------------------------


def draft_from_config(
    config: EngineStrategyConfig,
    metadata: dict[str, Any] | None = None,
) -> StrategyDraft:
    """Create a strategy draft from a configuration.

    Args:
        config: The strategy configuration.
        metadata: Optional metadata (source, author, etc.).

    Returns:
        A StrategyDraft in DRAFT state.
    """
    return StrategyDraft(
        config=config,
        state=StrategyState.DRAFT,
        metadata=metadata or {},
    )


def validate_draft(
    draft: StrategyDraft,
    available_indicators: set[str] | None = None,
) -> ValidatedStrategy:
    """Validate a strategy draft and transition to VALIDATED state.

    Args:
        draft: The draft to validate.
        available_indicators: Known indicator names for validation.

    Returns:
        ValidatedStrategy if validation passes.

    Raises:
        LifecycleError: If the draft is not in DRAFT state.
        LifecycleError: If validation fails (with error details).
    """
    if draft.state != StrategyState.DRAFT:
        raise LifecycleError(
            f"Cannot validate strategy in state '{draft.state.value}' "
            f"(expected '{StrategyState.DRAFT.value}')"
        )

    result = validate(draft.config, available_indicators=available_indicators)

    if not result.valid:
        raise LifecycleError(f"Strategy validation failed: {'; '.join(result.errors)}")

    return ValidatedStrategy(
        config=draft.config,
        state=StrategyState.VALIDATED,
        validation_result=result,
    )


def submit_for_backtest(validated: ValidatedStrategy) -> BacktestReadyStrategy:
    """Compile and submit a validated strategy for backtesting.

    Args:
        validated: The validated strategy to submit.

    Returns:
        BacktestReadyStrategy with compiled strategy.

    Raises:
        LifecycleError: If the strategy is not in VALIDATED state.
        LifecycleError: If compilation fails.
    """
    if validated.state != StrategyState.VALIDATED:
        raise LifecycleError(
            f"Cannot submit for backtest in state '{validated.state.value}' "
            f"(expected '{StrategyState.VALIDATED.value}')"
        )

    try:
        compiled = compile(validated.config)
    except CompilationError as exc:
        raise LifecycleError(f"Compilation failed: {exc}") from exc

    return BacktestReadyStrategy(
        config=validated.config,
        compiled=compiled,
    )
