"""Unified error types for PnLClaw.

Every error code maps to an HTTP status code for consistent API responses.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# ErrorCode — each code maps to an HTTP status
# ---------------------------------------------------------------------------


class ErrorCode(str, Enum):
    """Machine-readable error codes with HTTP status mapping."""

    # 400
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_PARAMETER = "INVALID_PARAMETER"
    INVALID_STRATEGY = "INVALID_STRATEGY"

    # 401
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"

    # 403
    RISK_DENIED = "RISK_DENIED"
    PERMISSION_DENIED = "PERMISSION_DENIED"

    # 404
    NOT_FOUND = "NOT_FOUND"

    # 409
    CONFLICT = "CONFLICT"

    # 429
    RATE_LIMITED = "RATE_LIMITED"

    # 502
    EXCHANGE_ERROR = "EXCHANGE_ERROR"

    # 503
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"

    # 500
    INTERNAL_ERROR = "INTERNAL_ERROR"


#: Mapping from ErrorCode to HTTP status code.
ERROR_CODE_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.VALIDATION_ERROR: 400,
    ErrorCode.INVALID_PARAMETER: 400,
    ErrorCode.INVALID_STRATEGY: 400,
    ErrorCode.AUTHENTICATION_ERROR: 401,
    ErrorCode.RISK_DENIED: 403,
    ErrorCode.PERMISSION_DENIED: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CONFLICT: 409,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.EXCHANGE_ERROR: 502,
    ErrorCode.SERVICE_UNAVAILABLE: 503,
    ErrorCode.INTERNAL_ERROR: 500,
}


# ---------------------------------------------------------------------------
# PnLClawError base
# ---------------------------------------------------------------------------


class PnLClawError(Exception):
    """Base exception for all PnLClaw errors.

    Attributes:
        code: Machine-readable error code.
        message: Human-readable description.
        details: Optional additional context.
        http_status: Corresponding HTTP status code.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.details = details
        self.http_status = ERROR_CODE_HTTP_STATUS.get(code, 500)
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for API error responses."""
        result: dict[str, Any] = {
            "code": self.code.value,
            "message": self.message,
        }
        if self.details is not None:
            result["details"] = self.details
        return result


# ---------------------------------------------------------------------------
# Subclasses — convenience wrappers for common error types
# ---------------------------------------------------------------------------


class ValidationError(PnLClawError):
    """Input validation failed."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCode.VALIDATION_ERROR, message, details)


class NotFoundError(PnLClawError):
    """Requested resource not found."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCode.NOT_FOUND, message, details)


class ExchangeError(PnLClawError):
    """Exchange communication failure."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCode.EXCHANGE_ERROR, message, details)


class RiskDeniedError(PnLClawError):
    """Action blocked by risk engine."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCode.RISK_DENIED, message, details)


class RateLimitedError(PnLClawError):
    """Rate limit exceeded."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCode.RATE_LIMITED, message, details)


class InternalError(PnLClawError):
    """Unexpected internal error."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCode.INTERNAL_ERROR, message, details)
