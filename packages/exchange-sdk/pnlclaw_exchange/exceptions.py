"""Exchange-SDK specific exception types.

All exceptions inherit from :class:`pnlclaw_types.errors.ExchangeError` so callers
can catch either the specific exception or the general ``ExchangeError``.
"""

from __future__ import annotations

from typing import Any

from pnlclaw_types.errors import ExchangeError


class WebSocketConnectionError(ExchangeError):
    """WebSocket connection could not be established."""

    def __init__(
        self,
        message: str,
        *,
        exchange: str | None = None,
        url: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        extra: dict[str, Any] = {}
        if exchange is not None:
            extra["exchange"] = exchange
        if url is not None:
            extra["url"] = url
        if details:
            extra.update(details)
        super().__init__(message, details=extra or None)


class WebSocketSubscriptionError(ExchangeError):
    """Subscription request failed or was rejected by the exchange."""

    def __init__(
        self,
        message: str,
        *,
        streams: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        extra: dict[str, Any] = {}
        if streams is not None:
            extra["streams"] = streams
        if details:
            extra.update(details)
        super().__init__(message, details=extra or None)


class StallTimeoutError(ExchangeError):
    """No data received within the configured stall timeout period."""

    def __init__(
        self,
        message: str = "WebSocket stall detected: no data within timeout",
        *,
        idle_s: float | None = None,
        timeout_s: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        extra: dict[str, Any] = {}
        if idle_s is not None:
            extra["idle_s"] = idle_s
        if timeout_s is not None:
            extra["timeout_s"] = timeout_s
        if details:
            extra.update(details)
        super().__init__(message, details=extra or None)


class SequenceGapError(ExchangeError):
    """L2 orderbook sequence ID is not contiguous — snapshot must be refreshed."""

    def __init__(
        self,
        message: str = "Sequence gap detected in L2 orderbook",
        *,
        expected: int | None = None,
        received: int | None = None,
        symbol: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        extra: dict[str, Any] = {}
        if expected is not None:
            extra["expected"] = expected
        if received is not None:
            extra["received"] = received
        if symbol is not None:
            extra["symbol"] = symbol
        if details:
            extra.update(details)
        super().__init__(message, details=extra or None)


class SnapshotRecoveryError(ExchangeError):
    """REST snapshot fetch failed during L2 orderbook recovery."""

    def __init__(
        self,
        message: str = "Failed to recover L2 orderbook snapshot via REST",
        *,
        symbol: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        extra: dict[str, Any] = {}
        if symbol is not None:
            extra["symbol"] = symbol
        if details:
            extra.update(details)
        super().__init__(message, details=extra or None)
