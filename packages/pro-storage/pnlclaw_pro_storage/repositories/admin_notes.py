"""Admin note repository — internal notes attached to users by admins."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select

from pnlclaw_pro_storage.models import AdminNote
from pnlclaw_pro_storage.postgres import AsyncPostgresManager


class AdminNoteRepository:
    """Async repository for the ``admin_notes`` table."""

    def __init__(self, db: AsyncPostgresManager) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def create(
        self,
        user_id: uuid.UUID,
        admin_id: uuid.UUID,
        content: str,
    ) -> AdminNote:
        """Create a new admin note on a user and return the persisted row."""
        note = AdminNote(
            user_id=user_id,
            admin_id=admin_id,
            content=content,
        )
        async with self._db.session() as session:
            session.add(note)
            await session.flush()
            await session.refresh(note)
            return note

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def list_for_user(self, user_id: uuid.UUID) -> list[AdminNote]:
        """Return all admin notes for a user, newest first."""
        async with self._db.session() as session:
            stmt = select(AdminNote).where(AdminNote.user_id == user_id).order_by(AdminNote.created_at.desc())
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete(self, note_id: uuid.UUID) -> None:
        """Remove a single admin note."""
        async with self._db.session() as session:
            stmt = delete(AdminNote).where(AdminNote.id == note_id)
            await session.execute(stmt)
