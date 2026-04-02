"""Auth-specific error classes.

All errors extend ``PnLClawError`` from ``pnlclaw_types.errors`` so that
the API layer can translate them into consistent HTTP error responses.
"""

from __future__ import annotations

from typing import Any

from pnlclaw_types.errors import ErrorCode, PnLClawError


class AuthenticationError(PnLClawError):
    """Generic authentication failure."""

    def __init__(self, message: str = "Authentication failed", details: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCode.AUTHENTICATION_ERROR, message, details)


class TokenExpiredError(PnLClawError):
    """The supplied token has expired."""

    def __init__(self, message: str = "Token has expired", details: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCode.AUTHENTICATION_ERROR, message, details)


class InvalidTokenError(PnLClawError):
    """The supplied token is malformed or has an invalid signature."""

    def __init__(self, message: str = "Invalid token", details: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCode.AUTHENTICATION_ERROR, message, details)


class OAuthError(PnLClawError):
    """An error occurred during an OAuth flow."""

    def __init__(self, message: str = "OAuth error", details: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCode.AUTHENTICATION_ERROR, message, details)


class AccountSuspendedError(PnLClawError):
    """The user account has been suspended."""

    def __init__(self, message: str = "Account suspended", details: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCode.PERMISSION_DENIED, message, details)


class AccountBannedError(PnLClawError):
    """The user account has been permanently banned."""

    def __init__(self, message: str = "Account banned", details: dict[str, Any] | None = None) -> None:
        super().__init__(ErrorCode.PERMISSION_DENIED, message, details)


class TOTPRequiredError(PnLClawError):
    """Two-factor TOTP verification is required to proceed."""

    def __init__(
        self,
        message: str = "TOTP verification required",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(ErrorCode.AUTHENTICATION_ERROR, message, details)
