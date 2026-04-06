"""Structured output schemas for LLM generation.

Provides JSON Schema extraction from Pydantic models and a typed
parsing helper. Distilled from OpenClaw structured output via
function calling pattern.
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, Field, ValidationError

from pnlclaw_llm.base import LLMError

T = TypeVar("T", bound=BaseModel)


# ---------------------------------------------------------------------------
# Native Function Calling schemas (v0.1.1)
# ---------------------------------------------------------------------------


class ToolCall(BaseModel):
    """A single tool invocation returned by the LLM via native function calling."""

    id: str = Field(..., description="Unique identifier for this tool call")
    name: str = Field(..., description="Name of the tool to invoke")
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Arguments to pass to the tool",
    )


class TokenUsage(BaseModel):
    """Token usage statistics from the LLM response."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ToolCallResult(BaseModel):
    """Result of a chat_with_tools() invocation.

    Wraps both tool calls and optional text content into a single
    structured response, allowing callers to handle both paths uniformly.
    """

    tool_calls: list[ToolCall] = Field(default_factory=list)
    text: str | None = None
    model: str = ""
    usage: TokenUsage = Field(default_factory=TokenUsage)


def get_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Extract a JSON Schema dict from a Pydantic model class.

    Args:
        model: A Pydantic BaseModel subclass.

    Returns:
        JSON Schema dictionary suitable for LLM structured output constraints.
    """
    return model.model_json_schema()


def extract_structured(raw_json: str, schema: type[T]) -> T:
    """Parse a raw JSON string into a validated Pydantic model instance.

    Args:
        raw_json: Raw JSON string (typically from LLM output).
        schema: Target Pydantic model class for validation.

    Returns:
        Validated model instance.

    Raises:
        LLMError: If JSON is malformed or validation fails, with a clear
            error message describing what went wrong.
    """
    import json

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise LLMError(
            f"Failed to parse LLM output as JSON: {exc}. Raw output (first 200 chars): {raw_json[:200]}"
        ) from exc

    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        raise LLMError(f"LLM output does not match {schema.__name__} schema: {exc}") from exc


# ---------------------------------------------------------------------------
# Pre-built schema accessors for common PnLClaw models
# ---------------------------------------------------------------------------


def trade_intent_schema() -> dict[str, Any]:
    """JSON Schema for ``TradeIntent`` (lazy import to avoid circular deps)."""
    from pnlclaw_types.agent import TradeIntent

    return get_json_schema(TradeIntent)


def strategy_config_schema() -> dict[str, Any]:
    """JSON Schema for ``StrategyConfig``."""
    from pnlclaw_types.strategy import StrategyConfig

    return get_json_schema(StrategyConfig)


def market_analysis_schema() -> dict[str, Any]:
    """JSON Schema for ``MarketAnalysis``.

    MarketAnalysis is a lightweight model for LLM-generated market
    assessment. Defined inline here as it is specific to LLM output
    and not part of the core shared-types.
    """
    return get_json_schema(MarketAnalysis)


class MarketAnalysis(BaseModel):
    """LLM-generated market analysis output."""

    symbol: str
    summary: str
    regime: str  # trending / ranging / volatile
    trend_direction: str  # bullish / bearish / neutral
    confidence: float
    key_levels: dict[str, float] = Field(default_factory=dict)
    recommendation: str = ""
