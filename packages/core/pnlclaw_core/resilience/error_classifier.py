"""Semantic error classification for retry and failover decisions."""

from __future__ import annotations

import socket
from enum import Enum


class ErrorCategory(str, Enum):
    """Semantic categories for classifying exceptions."""

    RATE_LIMIT = "rate_limit"
    AUTH = "auth"
    TIMEOUT = "timeout"
    NETWORK = "network"
    BILLING = "billing"
    UNKNOWN = "unknown"


def classify_error(exc: Exception) -> ErrorCategory:
    """Classify an exception into a semantic category.

    Uses exception type and message heuristics. Designed for exchange API,
    LLM provider, and HTTP client errors.

    Args:
        exc: The exception to classify.

    Returns:
        The most appropriate ``ErrorCategory``.
    """
    msg = str(exc).lower()

    # Timeout
    if isinstance(exc, (TimeoutError, asyncio_timeout_types())):
        return ErrorCategory.TIMEOUT
    if "timeout" in msg or "timed out" in msg:
        return ErrorCategory.TIMEOUT

    # Network
    if isinstance(exc, (ConnectionError, OSError, socket.error)):
        return ErrorCategory.NETWORK
    if any(k in msg for k in ("connection", "dns", "resolve", "unreachable", "reset")):
        return ErrorCategory.NETWORK

    # Rate limiting
    if "429" in msg or "rate limit" in msg or "too many requests" in msg:
        return ErrorCategory.RATE_LIMIT
    if "retry-after" in msg:
        return ErrorCategory.RATE_LIMIT

    # Auth
    if "401" in msg or "403" in msg or "unauthorized" in msg or "forbidden" in msg:
        return ErrorCategory.AUTH
    if "invalid api key" in msg or "authentication" in msg:
        return ErrorCategory.AUTH

    # Billing
    if "402" in msg or "payment" in msg or "quota" in msg or "billing" in msg:
        return ErrorCategory.BILLING
    if "insufficient" in msg and "funds" in msg:
        return ErrorCategory.BILLING

    return ErrorCategory.UNKNOWN


def asyncio_timeout_types() -> tuple[type, ...]:
    """Return asyncio timeout exception types (version-safe)."""
    import asyncio

    types: list[type] = [asyncio.TimeoutError]
    return tuple(types)
