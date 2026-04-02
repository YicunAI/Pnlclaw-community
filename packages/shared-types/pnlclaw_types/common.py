"""Common shared types used across all PnLClaw packages."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Timestamp — millisecond-precision epoch (standard in crypto exchanges)
# ---------------------------------------------------------------------------

Timestamp = int
"""Millisecond-precision Unix epoch timestamp."""


# ---------------------------------------------------------------------------
# Symbol — normalized trading pair identifier
# ---------------------------------------------------------------------------

Symbol = str
"""Normalized trading pair, e.g. ``"BTC/USDT"``."""


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class Pagination(BaseModel):
    """Cursor-style pagination metadata."""

    offset: int = Field(0, ge=0, description="Number of items to skip")
    limit: int = Field(50, ge=1, le=1000, description="Max items per page")
    total: int = Field(0, ge=0, description="Total items available")

    model_config = ConfigDict(json_schema_extra={"examples": [{"offset": 0, "limit": 50, "total": 120}]})


# ---------------------------------------------------------------------------
# ErrorInfo
# ---------------------------------------------------------------------------


class ErrorInfo(BaseModel):
    """Structured error information returned in API responses."""

    code: str = Field(..., description="Machine-readable error code, e.g. 'VALIDATION_ERROR'")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] | None = Field(None, description="Optional additional error context")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "code": "VALIDATION_ERROR",
                    "message": "Invalid symbol format",
                    "details": {"field": "symbol", "value": "btcusdt"},
                }
            ]
        }
    )


# ---------------------------------------------------------------------------
# APIResponse[T] — generic envelope for all API responses
# ---------------------------------------------------------------------------


class ResponseMeta(BaseModel):
    """Metadata attached to every API response."""

    request_id: str | None = Field(None, description="Unique request identifier")
    pagination: Pagination | None = Field(None, description="Pagination info if applicable")

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"request_id": "550e8400-e29b-41d4-a716-446655440000", "pagination": None}]}
    )


class APIResponse(BaseModel, Generic[T]):
    """Standard API response envelope wrapping data, meta, and error."""

    data: T | None = Field(None, description="Response payload")
    meta: ResponseMeta | None = Field(None, description="Response metadata")
    error: ErrorInfo | None = Field(None, description="Error info, present on failure")

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "data": {"symbol": "BTC/USDT", "price": 67000.0},
                    "meta": {"request_id": "abc-123", "pagination": None},
                    "error": None,
                }
            ]
        }
    )
