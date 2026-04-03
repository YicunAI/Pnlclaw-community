"""Lightweight audit logging for critical local-api operations.

Writes structured events to the SQLite audit_logs table via
the existing ``AuditLogRepository``. Non-blocking: logs a warning
on failure but never raises to avoid disrupting business logic.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_audit_repo: Any = None


def set_audit_repo(repo: Any) -> None:
    global _audit_repo
    _audit_repo = repo


async def audit_event(
    *,
    event_type: str,
    actor: str,
    action: str,
    resource: str = "",
    outcome: str = "success",
    severity: str = "info",
    details: dict[str, Any] | None = None,
) -> None:
    """Append an audit event. Fails silently to avoid blocking the caller."""
    if _audit_repo is None:
        return
    try:
        await _audit_repo.append(
            {
                "event_type": event_type,
                "actor": actor,
                "action": action,
                "resource": resource,
                "outcome": outcome,
                "severity": severity,
                "details": details or {},
            }
        )
    except Exception:
        logger.warning("Failed to write audit event: %s/%s", event_type, action, exc_info=True)
