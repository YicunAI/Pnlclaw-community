"""Internal event types for PnLClaw event bus.

Used by diagnostics, hooks, and the internal event bus — not exposed via API.
All events carry ``sequence_id`` and ``timestamp`` for ordering.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pnlclaw_types.common import Timestamp

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DiagnosticLevel(str, Enum):
    """Severity level for diagnostic events."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# DiagnosticEvent
# ---------------------------------------------------------------------------


class DiagnosticEvent(BaseModel):
    """Internal diagnostic event for observability and troubleshooting."""

    sequence_id: int = Field(..., ge=0, description="Monotonic sequence number for ordering")
    timestamp: Timestamp = Field(..., description="Event time (ms epoch)")
    category: str = Field(..., description="Event category, e.g. 'market', 'order', 'llm'")
    level: DiagnosticLevel = Field(..., description="Severity level")
    message: str = Field(..., description="Human-readable event description")
    data: dict[str, Any] | None = Field(None, description="Optional structured payload")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "sequence_id": 1,
                    "timestamp": 1711000000000,
                    "category": "market",
                    "level": "info",
                    "message": "WebSocket connected to binance",
                    "data": {"exchange": "binance", "symbols": ["BTC/USDT"]},
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# HookEvent
# ---------------------------------------------------------------------------


class HookEvent(BaseModel):
    """Event fired by the internal hook system."""

    sequence_id: int = Field(..., ge=0, description="Monotonic sequence number for ordering")
    timestamp: Timestamp = Field(..., description="Event time (ms epoch)")
    hook_name: str = Field(
        ...,
        description="Hook identifier, e.g. 'on_market_tick', 'on_signal', 'on_order_placed'",
    )
    payload: dict[str, Any] = Field(default_factory=dict, description="Hook-specific data")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "sequence_id": 42,
                    "timestamp": 1711000000000,
                    "hook_name": "on_order_placed",
                    "payload": {
                        "order_id": "ord-001",
                        "symbol": "BTC/USDT",
                        "side": "buy",
                    },
                }
            ]
        }
    )
