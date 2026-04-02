"""Invitation repository — invite-code CRUD and redemption logic."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update

from pnlclaw_pro_storage.models import Invitation
from pnlclaw_pro_storage.postgres import AsyncPostgresManager


class InvitationRepository:
    """Async repository for the ``invitations`` table."""

    def __init__(self, db: AsyncPostgresManager) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create(
        self,
        code: str,
        created_by: uuid.UUID,
        max_uses: int = 1,
        expires_at: datetime | None = None,
    ) -> Invitation:
        """Insert a new invitation and return the persisted instance."""
        invitation = Invitation(
            code=code,
            created_by=created_by,
            max_uses=max_uses,
            expires_at=expires_at,
        )
        async with self._db.session() as session:
            session.add(invitation)
            await session.flush()
            await session.refresh(invitation)
            return invitation

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_code(self, code: str) -> Invitation | None:
        """Return an invitation by its unique code, or ``None``."""
        async with self._db.session() as session:
            stmt = select(Invitation).where(Invitation.code == code)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_all(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Invitation]:
        """Return a page of invitations ordered by creation date."""
        async with self._db.session() as session:
            stmt = (
                select(Invitation)
                .order_by(Invitation.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete(self, invitation_id: uuid.UUID) -> None:
        """Delete an invitation by its primary key."""
        async with self._db.session() as session:
            stmt = delete(Invitation).where(Invitation.id == invitation_id)
            await session.execute(stmt)

    # ------------------------------------------------------------------
    # Use (redeem)
    # ------------------------------------------------------------------

    async def use(
        self,
        code: str,
        used_by: uuid.UUID,
    ) -> Invitation | None:
        """Redeem an invitation code.

        Increments ``use_count``, sets ``used_by``, and returns the
        updated invitation.  Returns ``None`` if the code does not exist,
        has already reached ``max_uses``, or has expired.
        """
        now = datetime.now(timezone.utc)
        async with self._db.session() as session:
            stmt = select(Invitation).where(Invitation.code == code)
            result = await session.execute(stmt)
            invitation = result.scalar_one_or_none()

            if invitation is None:
                return None

            # Check expiry
            if invitation.expires_at is not None and invitation.expires_at <= now:
                return None

            # Check usage limit
            if invitation.use_count >= invitation.max_uses:
                return None

            invitation.use_count += 1
            invitation.used_by = used_by
            await session.flush()
            await session.refresh(invitation)
            return invitation

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def cleanup_expired(self) -> int:
        """Delete invitations that have expired.

        Returns the number of rows removed.
        """
        now = datetime.now(timezone.utc)
        async with self._db.session() as session:
            stmt = delete(Invitation).where(
                Invitation.expires_at.isnot(None),
                Invitation.expires_at < now,
            )
            result = await session.execute(stmt)
            return result.rowcount  # type: ignore[return-value]
