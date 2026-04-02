"""Session lifecycle management with token rotation.

Coordinates between :class:`JWTManager` and the underlying database
repositories (``SessionRepository`` / ``RefreshToken`` from pro-storage).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID

from pnlclaw_pro_auth.config import AuthConfig
from pnlclaw_pro_auth.errors import AuthenticationError, InvalidTokenError
from pnlclaw_pro_auth.jwt_manager import JWTManager
from pnlclaw_pro_auth.models import TokenPair

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Repository protocols — depend on abstractions, not pro-storage concrete types
# ---------------------------------------------------------------------------


class SessionRepository(Protocol):
    """Minimal interface for the session persistence layer."""

    async def create(
        self,
        user_id: str,
        jti: str,
        ip_address: str | None,
        user_agent: str | None,
        expires_at: datetime,
    ) -> UUID:
        """Persist a new session and return its ID."""
        ...

    async def get_by_jti(self, jti: str) -> dict | None:
        """Return session dict by JTI, or None."""
        ...

    async def get_by_id(self, session_id: UUID) -> dict | None:
        """Return session dict by session ID, or None."""
        ...

    async def revoke(self, jti: str) -> None:
        """Soft-revoke a session by JTI."""
        ...

    async def revoke_all_for_user(self, user_id: str) -> int:
        """Revoke all active sessions for a user. Return count revoked."""
        ...


class RefreshTokenRepository(Protocol):
    """Minimal interface for refresh token persistence."""

    async def create(
        self,
        session_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        """Persist a new refresh token."""
        ...

    async def get_by_hash(self, token_hash: str) -> dict | None:
        """Return refresh token record by hash, or None."""
        ...

    async def mark_used(self, token_hash: str) -> None:
        """Mark a refresh token as used (consumed)."""
        ...

    async def revoke_all_for_session(self, session_id: UUID) -> None:
        """Revoke all refresh tokens for a session."""
        ...

    async def revoke_all_for_user(self, user_id: str) -> None:
        """Revoke all refresh tokens for all sessions of a user."""
        ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_token(token: str) -> str:
    """SHA-256 hash a refresh token for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------


class SessionManager:
    """Issue, rotate, and revoke user sessions.

    Args:
        jwt_manager: JWT encoding/decoding helper.
        session_repo: Persistence for session records.
        refresh_repo: Persistence for refresh token records.
        config: Auth configuration (expiry durations etc.).
    """

    def __init__(
        self,
        jwt_manager: JWTManager,
        session_repo: SessionRepository,
        refresh_repo: RefreshTokenRepository,
        config: AuthConfig,
    ) -> None:
        self._jwt = jwt_manager
        self._sessions = session_repo
        self._refresh = refresh_repo
        self._config = config

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_session(
        self,
        user_id: str,
        role: str,
        ip: str,
        user_agent: str,
        display_name: str = "",
        avatar_url: str = "",
    ) -> TokenPair:
        """Create a new session and return an access + refresh token pair."""
        access_delta = timedelta(minutes=self._config.access_token_expire_minutes)
        refresh_delta = timedelta(days=self._config.refresh_token_expire_days)

        access_token, jti = self._jwt.create_access_token(
            user_id=user_id,
            role=role,
            expires_delta=access_delta,
            name=display_name,
            avatar_url=avatar_url,
        )

        session_expires = datetime.now(timezone.utc) + refresh_delta
        session_id = await self._sessions.create(
            user_id=user_id,
            jti=jti,
            ip_address=ip,
            user_agent=user_agent,
            expires_at=session_expires,
        )

        refresh_token = self._jwt.create_refresh_token(
            session_id=str(session_id),
            expires_delta=refresh_delta,
        )
        await self._refresh.create(
            session_id=session_id,
            token_hash=_hash_token(refresh_token),
            expires_at=session_expires,
        )

        logger.info("Session created for user=%s jti=%s", user_id, jti)
        return TokenPair(access_token=access_token, refresh_token=refresh_token)

    # ------------------------------------------------------------------
    # Refresh (with rotation)
    # ------------------------------------------------------------------

    async def refresh_session(
        self,
        refresh_token: str,
        extra_claims: dict[str, str] | None = None,
    ) -> TokenPair:
        """Rotate a refresh token and return a new token pair.

        The old refresh token is marked as used and a brand-new pair is
        issued.  If the old token has already been used, all tokens for
        the session are revoked (replay detection).

        Args:
            refresh_token: The current refresh token to rotate.
            extra_claims: Optional profile claims (name, avatar_url) to
                embed in the new access token.

        Raises:
            InvalidTokenError: If the refresh token cannot be decoded.
            AuthenticationError: If the token has already been consumed
                or the session is revoked.
        """
        payload = self._jwt.decode_refresh_token(refresh_token)

        session_id_str: str = payload.get("sid", "")
        token_hash = _hash_token(refresh_token)

        try:
            session_uuid = UUID(session_id_str)
        except ValueError:
            raise InvalidTokenError("Invalid session ID in refresh token")

        # Look up the stored refresh token
        stored = await self._refresh.get_by_hash(token_hash)
        if stored is None:
            raise AuthenticationError("Refresh token not recognised")

        # Replay detection — revoke all refresh tokens AND the session itself
        if stored.get("used_at") is not None or stored.get("revoked_at") is not None:
            logger.warning(
                "Refresh token replay detected for session=%s — revoking all",
                session_id_str,
            )
            await self._refresh.revoke_all_for_session(session_uuid)
            session = await self._sessions.get_by_id(session_uuid)
            if session and session.get("jti"):
                await self._sessions.revoke(session["jti"])
            raise AuthenticationError("Refresh token has already been used")

        # Mark old token as consumed
        await self._refresh.mark_used(token_hash)

        # Look up the session to get authoritative user info (H1)
        session = await self._sessions.get_by_id(session_uuid)
        if session is None:
            raise AuthenticationError("Session not found or has been revoked")
        if session.get("revoked_at") is not None:
            raise AuthenticationError("Session has been revoked")

        user_id: str = session.get("user_id", "")
        role: str = session.get("role", "user")
        if not user_id:
            raise AuthenticationError("Session record missing user_id")

        access_delta = timedelta(minutes=self._config.access_token_expire_minutes)
        refresh_delta = timedelta(days=self._config.refresh_token_expire_days)

        kw: dict[str, str] = {}
        if extra_claims:
            kw.update(extra_claims)

        new_access, new_jti = self._jwt.create_access_token(
            user_id=user_id,
            role=role,
            expires_delta=access_delta,
            **kw,
        )

        new_refresh = self._jwt.create_refresh_token(
            session_id=session_id_str,
            expires_delta=refresh_delta,
        )
        new_expires = datetime.now(timezone.utc) + refresh_delta

        await self._refresh.create(
            session_id=session_uuid,
            token_hash=_hash_token(new_refresh),
            expires_at=new_expires,
        )

        logger.info("Session refreshed session=%s new_jti=%s", session_id_str, new_jti)
        return TokenPair(access_token=new_access, refresh_token=new_refresh)

    # ------------------------------------------------------------------
    # Revoke
    # ------------------------------------------------------------------

    async def revoke_session(self, jti: str) -> None:
        """Revoke a single session by its JTI.

        Also revokes all refresh tokens associated with the session.
        """
        session = await self._sessions.get_by_jti(jti)
        await self._sessions.revoke(jti)
        # Also revoke all refresh tokens for this session (H5)
        if session and session.get("id"):
            session_id = session["id"]
            if not isinstance(session_id, UUID):
                session_id = UUID(str(session_id))
            await self._refresh.revoke_all_for_session(session_id)
        logger.info("Session revoked jti=%s", jti)

    async def revoke_all_user_sessions(self, user_id: str) -> int:
        """Revoke every active session belonging to a user.

        Also revokes all refresh tokens for each session.

        Returns:
            The number of sessions revoked.
        """
        count = await self._sessions.revoke_all_for_user(user_id)
        # Also revoke all refresh tokens for this user's sessions (H6)
        await self._refresh.revoke_all_for_user(user_id)
        logger.info("All sessions revoked for user=%s count=%d", user_id, count)
        return count
