"""Admin audit repository — records of administrative actions."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select

from pnlclaw_pro_storage.models import AdminAudit
from pnlclaw_pro_storage.postgres import AsyncPostgresManager


class AdminAuditRepository:
    """Async repository for the ``admin_audit`` table."""

    def __init__(self, db: AsyncPostgresManager) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def log(
        self,
        admin_user_id: uuid.UUID,
        action: str,
        target_user_id: uuid.UUID | None = None,
        details: dict | None = None,
        ip_address: str | None = None,
    ) -> None:
        """Record an admin action."""
        entry = AdminAudit(
            admin_user_id=admin_user_id,
            action=action,
            target_user_id=target_user_id,
            details=details or {},
            ip_address=ip_address,
        )
        async with self._db.session() as session:
            session.add(entry)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def query(
        self,
        *,
        admin_user_id: uuid.UUID | None = None,
        action: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[AdminAudit]:
        """Return audit entries matching the given filters."""
        async with self._db.session() as session:
            stmt = select(AdminAudit)

            if admin_user_id is not None:
                stmt = stmt.where(AdminAudit.admin_user_id == admin_user_id)
            if action is not None:
                stmt = stmt.where(AdminAudit.action == action)
            if start is not None:
                stmt = stmt.where(AdminAudit.created_at >= start)
            if end is not None:
                stmt = stmt.where(AdminAudit.created_at <= end)

            stmt = stmt.order_by(AdminAudit.created_at.desc()).offset(offset).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())
