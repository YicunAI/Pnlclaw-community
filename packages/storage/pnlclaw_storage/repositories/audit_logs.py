"""Audit log append-only repository.

Writes audit events to the ``audit_logs`` table and supports
time-range + event-type queries. Results are returned in reverse
chronological order (newest first).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from pnlclaw_storage.sqlite import AsyncSQLiteManager


class AuditLogRepository:
    """Append-only audit log with time-based querying.

    Args:
        db: An initialized ``AsyncSQLiteManager`` instance.
    """

    def __init__(self, db: AsyncSQLiteManager) -> None:
        self._db = db

    async def append(self, event: dict[str, Any]) -> str:
        """Append an audit event.

        Expected keys: event_type (required), plus optional severity,
        actor, action, resource, outcome, details (dict).

        An ``id`` is auto-generated if not provided.

        Returns:
            The event ID.
        """
        event_id = event.get("id", str(uuid.uuid4()))
        now = datetime.now(timezone.utc).isoformat()
        details = event.get("details", {})
        details_json = json.dumps(details, default=str)

        await self._db.execute(
            """
            INSERT INTO audit_logs
                (id, timestamp, event_type, severity, actor,
                 action, resource, outcome, details_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                event.get("timestamp", now),
                event["event_type"],
                event.get("severity", "info"),
                event.get("actor", ""),
                event.get("action", ""),
                event.get("resource", ""),
                event.get("outcome", ""),
                details_json,
            ),
        )
        return event_id

    async def query(
        self,
        event_type: str | None = None,
        since: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query audit logs with optional filters.

        Args:
            event_type: Filter by event type (exact match).
            since: ISO-format datetime; only return events at or after
                this timestamp.
            limit: Maximum number of results (default 100).

        Returns:
            List of event dicts, newest first.
        """
        clauses: list[str] = []
        params: list[Any] = []

        if event_type is not None:
            clauses.append("event_type = ?")
            params.append(event_type)

        if since is not None:
            clauses.append("timestamp >= ?")
            params.append(since)

        where = ""
        if clauses:
            where = "WHERE " + " AND ".join(clauses)

        params.append(limit)
        rows = await self._db.execute(
            f"""
            SELECT id, timestamp, event_type, severity, actor,
                   action, resource, outcome, details_json
            FROM audit_logs
            {where}
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            tuple(params),
        )

        results: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            raw = d.pop("details_json", "{}")
            try:
                d["details"] = json.loads(raw)
            except json.JSONDecodeError:
                d["details"] = raw
            results.append(d)
        return results
