"""Login history repository — per-login tracking with geo/device analytics."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select

from pnlclaw_pro_storage.models import LoginHistory
from pnlclaw_pro_storage.postgres import AsyncPostgresManager


class LoginHistoryRepository:
    """Async repository for the ``login_history`` table."""

    def __init__(self, db: AsyncPostgresManager) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def record(
        self,
        user_id: uuid.UUID,
        provider: str,
        ip_address: str | None = None,
        country: str | None = None,
        city: str | None = None,
        user_agent: str | None = None,
        device_type: str | None = None,
        os: str | None = None,
        browser: str | None = None,
        success: bool = True,
        failure_reason: str | None = None,
    ) -> LoginHistory:
        """Record a login attempt and return the persisted row."""
        entry = LoginHistory(
            user_id=user_id,
            provider=provider,
            ip_address=ip_address,
            country=country,
            city=city,
            user_agent=user_agent,
            device_type=device_type,
            os=os,
            browser=browser,
            success=success,
            failure_reason=failure_reason,
        )
        async with self._db.session() as session:
            session.add(entry)
            await session.flush()
            await session.refresh(entry)
            return entry

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_for_user(
        self,
        user_id: uuid.UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> list[LoginHistory]:
        """Return login history for a specific user, newest first."""
        async with self._db.session() as session:
            stmt = (
                select(LoginHistory)
                .where(LoginHistory.user_id == user_id)
                .order_by(LoginHistory.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    async def get_geo_distribution(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict]:
        """Aggregate logins by country.

        Returns a list of ``{"country": str, "count": int}`` dicts,
        ordered by count descending.
        """
        async with self._db.session() as session:
            stmt = select(
                LoginHistory.country,
                func.count().label("count"),
            ).where(LoginHistory.success.is_(True))

            if start is not None:
                stmt = stmt.where(LoginHistory.created_at >= start)
            if end is not None:
                stmt = stmt.where(LoginHistory.created_at <= end)

            stmt = stmt.group_by(LoginHistory.country).order_by(func.count().desc())
            result = await session.execute(stmt)
            return [{"country": row.country, "count": row.count} for row in result.all()]

    async def get_device_distribution(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict]:
        """Aggregate logins by device_type, os, and browser.

        Returns a list of dicts with ``device_type``, ``os``, ``browser``,
        and ``count`` keys, ordered by count descending.
        """
        async with self._db.session() as session:
            stmt = select(
                LoginHistory.device_type,
                LoginHistory.os,
                LoginHistory.browser,
                func.count().label("count"),
            ).where(LoginHistory.success.is_(True))

            if start is not None:
                stmt = stmt.where(LoginHistory.created_at >= start)
            if end is not None:
                stmt = stmt.where(LoginHistory.created_at <= end)

            stmt = stmt.group_by(
                LoginHistory.device_type,
                LoginHistory.os,
                LoginHistory.browser,
            ).order_by(func.count().desc())
            result = await session.execute(stmt)
            return [
                {
                    "device_type": row.device_type,
                    "os": row.os,
                    "browser": row.browser,
                    "count": row.count,
                }
                for row in result.all()
            ]

    async def get_login_stats(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict:
        """Return aggregate login statistics.

        Returns a dict with ``total``, ``success``, and ``failed`` counts.
        """
        async with self._db.session() as session:
            base = select(LoginHistory)

            if start is not None:
                base = base.where(LoginHistory.created_at >= start)
            if end is not None:
                base = base.where(LoginHistory.created_at <= end)

            subq = base.subquery()

            total_stmt = select(func.count()).select_from(subq)
            total: int = (await session.execute(total_stmt)).scalar_one()

            success_base = select(LoginHistory).where(LoginHistory.success.is_(True))
            if start is not None:
                success_base = success_base.where(LoginHistory.created_at >= start)
            if end is not None:
                success_base = success_base.where(LoginHistory.created_at <= end)
            success_subq = success_base.subquery()
            success_stmt = select(func.count()).select_from(success_subq)
            success: int = (await session.execute(success_stmt)).scalar_one()

            return {
                "total": total,
                "success": success,
                "failed": total - success,
            }
