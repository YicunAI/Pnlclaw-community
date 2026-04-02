"""Activity log repository — user action tracking and analytics queries."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from pnlclaw_pro_storage.models import ActivityLog
from pnlclaw_pro_storage.postgres import AsyncPostgresManager


class ActivityLogRepository:
    """Async repository for the ``activity_logs`` table."""

    def __init__(self, db: AsyncPostgresManager) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def log(
        self,
        user_id: uuid.UUID | None,
        event_type: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        path: str | None = None,
        method: str | None = None,
        details: dict | None = None,
    ) -> None:
        """Append an activity log entry (fire-and-forget style)."""
        entry = ActivityLog(
            user_id=user_id,
            event_type=event_type,
            ip_address=ip_address,
            user_agent=user_agent,
            path=path,
            method=method,
            details=details or {},
        )
        async with self._db.session() as session:
            session.add(entry)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def query(
        self,
        *,
        user_id: uuid.UUID | None = None,
        event_type: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[ActivityLog]:
        """Return activity log entries matching the given filters."""
        async with self._db.session() as session:
            stmt = select(ActivityLog)

            if user_id is not None:
                stmt = stmt.where(ActivityLog.user_id == user_id)
            if event_type is not None:
                stmt = stmt.where(ActivityLog.event_type == event_type)
            if start is not None:
                stmt = stmt.where(ActivityLog.created_at >= start)
            if end is not None:
                stmt = stmt.where(ActivityLog.created_at <= end)

            stmt = stmt.order_by(ActivityLog.created_at.desc()).offset(offset).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Analytics
    # ------------------------------------------------------------------

    async def count_active_users(self, period: timedelta) -> int:
        """Count distinct users with activity within the given period."""
        since = datetime.now(UTC) - period
        async with self._db.session() as session:
            stmt = select(func.count(func.distinct(ActivityLog.user_id))).where(
                ActivityLog.created_at >= since,
                ActivityLog.user_id.isnot(None),
            )
            result = await session.execute(stmt)
            return result.scalar_one()

    async def count_by_period(
        self,
        event_type: str,
        period: timedelta,
        granularity: str = "day",
    ) -> list[dict]:
        """Aggregate event counts by time bucket.

        Parameters
        ----------
        event_type:
            The event type to count.
        period:
            How far back to look.
        granularity:
            One of ``"hour"``, ``"day"``, ``"week"``, ``"month"``.

        Returns
        -------
        list[dict]
            Each dict has ``{"bucket": <datetime-string>, "count": int}``.
        """
        since = datetime.now(UTC) - period
        trunc_map = {
            "hour": "hour",
            "day": "day",
            "week": "week",
            "month": "month",
        }
        trunc = trunc_map.get(granularity, "day")

        async with self._db.session() as session:
            bucket = func.date_trunc(trunc, ActivityLog.created_at).label("bucket")
            stmt = (
                select(bucket, func.count().label("count"))
                .where(
                    ActivityLog.event_type == event_type,
                    ActivityLog.created_at >= since,
                )
                .group_by(bucket)
                .order_by(bucket)
            )
            result = await session.execute(stmt)
            return [{"bucket": str(row.bucket), "count": row.count} for row in result.all()]
