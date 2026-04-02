"""JWT creation and verification.

Uses PyJWT for token encoding/decoding with explicit algorithm pinning
to prevent algorithm-confusion attacks.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt

from pnlclaw_pro_auth.errors import InvalidTokenError, TokenExpiredError

logger = logging.getLogger(__name__)


class JWTManager:
    """Create and verify JWTs for PnLClaw Pro authentication.

    Args:
        secret_key: HMAC signing key.
        algorithm: Signing algorithm (default ``HS256``).
    """

    def __init__(self, secret_key: str, algorithm: str = "HS256") -> None:
        self._secret = secret_key
        self._algorithm = algorithm

    # ------------------------------------------------------------------
    # Access tokens
    # ------------------------------------------------------------------

    def create_access_token(
        self,
        user_id: str,
        role: str,
        expires_delta: timedelta | None = None,
        **extra_claims: str,
    ) -> tuple[str, str]:
        """Create a signed access token.

        Extra claims (e.g. ``name``, ``avatar_url``) are included in the
        payload so the frontend can display user profile information
        without an additional API call.

        Returns:
            A ``(token, jti)`` tuple.
        """
        jti = uuid4().hex
        now = datetime.now(UTC)
        exp = now + (expires_delta or timedelta(minutes=15))
        payload: dict = {
            "sub": user_id,
            "role": role,
            "jti": jti,
            "iat": now,
            "exp": exp,
            "type": "access",
        }
        _reserved = {"sub", "role", "jti", "iat", "exp", "type"}
        for k, v in extra_claims.items():
            if k not in _reserved and v:
                payload[k] = v
        token = jwt.encode(payload, self._secret, algorithm=self._algorithm)
        return token, jti

    # ------------------------------------------------------------------
    # Refresh tokens
    # ------------------------------------------------------------------

    def create_refresh_token(
        self,
        session_id: str,
        expires_delta: timedelta | None = None,
    ) -> str:
        """Create a signed refresh token bound to a session."""
        now = datetime.now(UTC)
        exp = now + (expires_delta or timedelta(days=7))
        payload = {
            "sid": session_id,
            "iat": now,
            "exp": exp,
            "type": "refresh",
        }
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    # ------------------------------------------------------------------
    # State tokens (OAuth CSRF)
    # ------------------------------------------------------------------

    def create_state_token(
        self,
        provider: str,
        nonce: str,
        code_verifier: str | None = None,
        expires_delta: timedelta | None = None,
        **extra_claims: str,
    ) -> str:
        """Create a short-lived state token for OAuth flows."""
        now = datetime.now(UTC)
        exp = now + (expires_delta or timedelta(minutes=5))
        payload: dict = {
            "provider": provider,
            "nonce": nonce,
            "iat": now,
            "exp": exp,
            "type": "oauth_state",
        }
        if code_verifier is not None:
            payload["code_verifier"] = code_verifier
        _reserved = {"provider", "nonce", "iat", "exp", "type", "code_verifier"}
        safe_extra = {k: v for k, v in extra_claims.items() if k not in _reserved}
        payload.update(safe_extra)
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def decode_state_token(self, token: str) -> dict:
        """Decode and validate an OAuth state token.

        Raises:
            TokenExpiredError: If the token has expired.
            InvalidTokenError: If the token is malformed or signature is invalid.
        """
        return self._decode(token, expected_type="oauth_state")

    # ------------------------------------------------------------------
    # Generic decode
    # ------------------------------------------------------------------

    def decode_access_token(self, token: str) -> dict:
        """Decode and validate an access token.

        Raises:
            TokenExpiredError: If the token has expired.
            InvalidTokenError: If the token is malformed, signature is invalid,
                or the token type is not ``access``.
        """
        return self._decode(token, expected_type="access")

    def decode_refresh_token(self, token: str) -> dict:
        """Decode and validate a refresh token.

        Raises:
            TokenExpiredError: If the token has expired.
            InvalidTokenError: If the token is malformed, signature is invalid,
                or the token type is not ``refresh``.
        """
        return self._decode(token, expected_type="refresh")

    def decode_token(self, token: str) -> dict:
        """Decode any token, returning its payload dict.

        .. deprecated::
            Prefer :meth:`decode_access_token` or :meth:`decode_refresh_token`
            for explicit type safety.  This method still works but logs a
            warning because it does not enforce the token type.

        Raises:
            TokenExpiredError: If the token has expired.
            InvalidTokenError: If the token is malformed or signature is invalid.
        """
        logger.warning(
            "decode_token() called without type checking — prefer decode_access_token() or decode_refresh_token()"
        )
        return self._decode(token)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _decode(self, token: str, expected_type: str | None = None) -> dict:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
            )
        except jwt.ExpiredSignatureError:
            raise TokenExpiredError()
        except jwt.InvalidTokenError as exc:
            raise InvalidTokenError(str(exc))

        if expected_type is not None and payload.get("type") != expected_type:
            raise InvalidTokenError(f"Expected token type '{expected_type}', got '{payload.get('type')}'")
        return payload
