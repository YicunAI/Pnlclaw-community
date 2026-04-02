"""Agent runtime data models for PnLClaw.

Covers trade intents, market state classification, chat messages,
agent roles, and streaming events.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pnlclaw_types.common import Symbol, Timestamp
from pnlclaw_types.trading import OrderSide, OrderType

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AgentRole(str, Enum):
    """Predefined agent personas for multi-agent collaboration."""

    MARKET_ANALYST = "market_analyst"
    STRATEGY_ARCHITECT = "strategy_architect"
    RISK_GUARDIAN = "risk_guardian"
    STRATEGY_CODER = "strategy_coder"


class MarketRegime(str, Enum):
    """Market environment classification."""

    TRENDING = "trending"
    RANGING = "ranging"
    VOLATILE = "volatile"


class AgentStreamEventType(str, Enum):
    """Types of events in an agent response stream."""

    TEXT_DELTA = "text_delta"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    THINKING = "thinking"
    REFLECTION = "reflection"
    DONE = "done"


# ---------------------------------------------------------------------------
# TradeIntent
# ---------------------------------------------------------------------------


class TradeIntent(BaseModel):
    """AI-generated trading intention (not yet an order).

    Must pass through risk validation before becoming an Order.
    """

    symbol: Symbol = Field(..., description="Target trading pair")
    side: OrderSide = Field(..., description="Intended direction")
    quantity: float = Field(..., gt=0, description="Intended quantity in base currency")
    price: float | None = Field(None, ge=0, description="Target price (None for market)")
    order_type: OrderType = Field(OrderType.MARKET, description="Intended order type")
    reasoning: str = Field(..., min_length=1, description="AI's reasoning for this trade")
    confidence: float = Field(..., ge=0.0, le=1.0, description="AI confidence score (0.0 to 1.0)")
    risk_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Risk parameters (stop_loss, take_profit, max_slippage, etc.)",
    )
    timestamp: Timestamp = Field(..., description="Intent generation time (ms epoch)")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "symbol": "BTC/USDT",
                    "side": "buy",
                    "quantity": 0.1,
                    "price": None,
                    "order_type": "market",
                    "reasoning": "SMA cross detected with strong volume confirmation",
                    "confidence": 0.82,
                    "risk_params": {
                        "stop_loss": 65000.0,
                        "take_profit": 70000.0,
                    },
                    "timestamp": 1711000000000,
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# MarketState
# ---------------------------------------------------------------------------


class MarketState(BaseModel):
    """Simplified market state classification for a symbol."""

    symbol: Symbol = Field(..., description="Trading pair")
    regime: MarketRegime = Field(..., description="Current market regime")
    trend_strength: float = Field(..., ge=0.0, le=1.0, description="Trend strength (0 = no trend, 1 = strong)")
    volatility: float = Field(..., ge=0.0, description="Volatility measure (annualized or normalized)")
    timestamp: Timestamp = Field(..., description="State assessment time (ms epoch)")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "symbol": "BTC/USDT",
                    "regime": "trending",
                    "trend_strength": 0.75,
                    "volatility": 0.45,
                    "timestamp": 1711000000000,
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# ChatMessage
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    """Single message in an agent conversation."""

    role: str = Field(..., description="Message role: 'user', 'assistant', 'system', or 'tool'")
    content: str = Field(..., description="Message content")
    timestamp: Timestamp = Field(..., description="Message time (ms epoch)")
    metadata: dict[str, Any] | None = Field(None, description="Optional metadata (tool_call_id, model, etc.)")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "role": "user",
                    "content": "Create a BTC SMA crossover strategy",
                    "timestamp": 1711000000000,
                    "metadata": None,
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# AgentStreamEvent
# ---------------------------------------------------------------------------


class AgentStreamEvent(BaseModel):
    """Event emitted during agent streaming response.

    Types: text_delta (partial text), tool_call (tool invocation),
    tool_result (tool output), done (stream complete).
    """

    type: AgentStreamEventType = Field(..., description="Event type")
    data: dict[str, Any] = Field(default_factory=dict, description="Event payload (varies by type)")
    timestamp: Timestamp = Field(..., description="Event time (ms epoch)")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "type": "text_delta",
                    "data": {"text": "Based on the current market..."},
                    "timestamp": 1711000000000,
                },
                {
                    "type": "tool_call",
                    "data": {"tool": "market_ticker", "args": {"symbol": "BTC/USDT"}},
                    "timestamp": 1711000000100,
                },
                {
                    "type": "done",
                    "data": {},
                    "timestamp": 1711000001000,
                },
            ]
        }
    )
