"""Session & refresh-token repository."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update

from pnlclaw_pro_storage.models import RefreshToken, Session
from pnlclaw_pro_storage.postgres import AsyncPostgresManager


class SessionRepository:
    """Async repository for the ``sessions`` and ``refresh_tokens`` tables."""

    def __init__(self, db: AsyncPostgresManager) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Session CRUD
    # ------------------------------------------------------------------

    async def create(
        self,
        user_id: uuid.UUID,
        jti: str,
        ip_address: str | None,
        user_agent: str | None,
        expires_at: datetime,
    ) -> Session:
        """Create a new session row."""
        session_obj = Session(
            user_id=user_id,
            jti=jti,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
        )
        async with self._db.session() as session:
            session.add(session_obj)
            await session.flush()
            await session.refresh(session_obj)
            return session_obj

    async def get_by_jti(self, jti: str) -> Session | None:
        """Look up a session by its JWT ID."""
        async with self._db.session() as session:
            stmt = select(Session).where(Session.jti == jti)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_active_for_user(self, user_id: uuid.UUID) -> list[Session]:
        """Return all non-revoked, non-expired sessions for a user."""
        now = datetime.now(timezone.utc)
        async with self._db.session() as session:
            stmt = (
                select(Session)
                .where(
                    Session.user_id == user_id,
                    Session.revoked_at.is_(None),
                    Session.expires_at > now,
                )
                .order_by(Session.created_at.desc())
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def revoke(self, session_id: uuid.UUID) -> None:
        """Mark a single session as revoked."""
        now = datetime.now(timezone.utc)
        async with self._db.session() as session:
            stmt = (
                update(Session)
                .where(Session.id == session_id)
                .values(revoked_at=now)
            )
            await session.execute(stmt)

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        """Revoke every active session for a user.

        Returns the number of sessions revoked.
        """
        now = datetime.now(timezone.utc)
        async with self._db.session() as session:
            stmt = (
                update(Session)
                .where(
                    Session.user_id == user_id,
                    Session.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            result = await session.execute(stmt)
            return result.rowcount  # type: ignore[return-value]

    async def cleanup_expired(self) -> int:
        """Delete sessions that have expired.

        Returns the number of rows removed.
        """
        now = datetime.now(timezone.utc)
        async with self._db.session() as session:
            stmt = delete(Session).where(Session.expires_at < now)
            result = await session.execute(stmt)
            return result.rowcount  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Refresh tokens
    # ------------------------------------------------------------------

    async def create_refresh_token(
        self,
        session_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> RefreshToken:
        """Create a refresh token tied to a session."""
        rt = RefreshToken(
            session_id=session_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        async with self._db.session() as session:
            session.add(rt)
            await session.flush()
            await session.refresh(rt)
            return rt

    async def get_refresh_token(self, token_hash: str) -> RefreshToken | None:
        """Look up a refresh token by its hash."""
        async with self._db.session() as session:
            stmt = select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.used_at.is_(None),
                RefreshToken.revoked_at.is_(None),
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def use_refresh_token(self, token_hash: str) -> None:
        """Mark a refresh token as used (single-use rotation)."""
        now = datetime.now(timezone.utc)
        async with self._db.session() as session:
            stmt = (
                update(RefreshToken)
                .where(RefreshToken.token_hash == token_hash)
                .values(used_at=now)
            )
            await session.execute(stmt)
