"""Security audit logger — JSONL format with automatic redaction.

Implements SE-01 audit trail: high-sensitivity operations (orders, config
changes, secret access, policy changes) are recorded to append-only JSONL files.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from pnlclaw_security.redaction import redact_text

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AuditSeverity(str, Enum):
    """Severity levels for audit events."""

    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"


class AuditEventType(str, Enum):
    """Categories of auditable actions."""

    TOOL_CALL = "tool_call"
    TOOL_BLOCKED = "tool_blocked"
    ORDER_INTENT = "order_intent"
    ORDER_EXECUTED = "order_executed"
    CONFIG_CHANGE = "config_change"
    SECRET_ACCESS = "secret_access"
    POLICY_CHANGE = "policy_change"
    INJECTION_DETECTED = "injection_detected"
    REDACTION_APPLIED = "redaction_applied"
    PAIRING_ATTEMPT = "pairing_attempt"
    GUARDRAIL_TRIGGERED = "guardrail_triggered"


# ---------------------------------------------------------------------------
# Audit event model
# ---------------------------------------------------------------------------


class AuditEvent(BaseModel):
    """A single auditable action."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = Field(default_factory=time.time)
    event_type: AuditEventType
    severity: AuditSeverity = AuditSeverity.INFO
    actor: str = Field(description="Who triggered: user, agent, system")
    action: str = Field(description="What was done")
    resource: str = Field(default="", description="What was acted upon")
    outcome: str = Field(default="allowed", description="allowed, blocked, warning")
    details: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Audit logger
# ---------------------------------------------------------------------------

# Default max file size before rotation (10 MB)
_DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024


class AuditLogger:
    """Append-only JSONL audit logger with automatic redaction and rotation.

    Args:
        log_dir: Directory for audit log files.
            Defaults to ``~/.pnlclaw/audit/``.
        max_file_size: Max bytes per log file before rotation.
    """

    def __init__(
        self,
        log_dir: Path | None = None,
        *,
        max_file_size: int = _DEFAULT_MAX_FILE_SIZE,
    ) -> None:
        self._log_dir = log_dir or Path.home() / ".pnlclaw" / "audit"
        self._max_file_size = max_file_size
        self._current_file: Path | None = None
        self._ensure_dir()

    def log(self, event: AuditEvent) -> None:
        """Write an audit event to the current log file.

        The ``details`` field is automatically redacted before writing
        to prevent accidental secret leakage into audit logs.
        """
        # Redact details values
        redacted_details = self._redact_details(event.details)
        record = event.model_copy(update={"details": redacted_details})

        line = record.model_dump_json() + "\n"
        self._atomic_append(line)

    def query(
        self,
        *,
        event_type: AuditEventType | None = None,
        since: float | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Query audit events from log files.

        Args:
            event_type: Filter by event type.
            since: Only events after this Unix timestamp.
            limit: Maximum number of events to return.

        Returns:
            List of matching audit events, newest first.
        """
        events: list[AuditEvent] = []
        log_files = sorted(self._log_dir.glob("audit-*.jsonl"), reverse=True)

        for log_file in log_files:
            if len(events) >= limit:
                break
            try:
                lines = log_file.read_text(encoding="utf-8").strip().splitlines()
            except OSError:
                continue

            for line in reversed(lines):
                if len(events) >= limit:
                    break
                if not line.strip():
                    continue
                try:
                    evt = AuditEvent.model_validate_json(line)
                except Exception:
                    continue

                if event_type and evt.event_type != event_type:
                    continue
                if since and evt.timestamp < since:
                    continue
                events.append(evt)

        return events

    # -- internal ------------------------------------------------------------

    def _ensure_dir(self) -> None:
        """Create the log directory if it doesn't exist."""
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def _get_current_file(self) -> Path:
        """Get the current log file, rotating if necessary."""
        if self._current_file and self._current_file.exists():
            if self._current_file.stat().st_size < self._max_file_size:
                return self._current_file

        # Create new file with date and sequence number
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        seq = 1
        while True:
            candidate = self._log_dir / f"audit-{date_str}-{seq:03d}.jsonl"
            if not candidate.exists() or candidate.stat().st_size < self._max_file_size:
                self._current_file = candidate
                return candidate
            seq += 1

    def _atomic_append(self, line: str) -> None:
        """Append a line to the current log file with flush + fsync."""
        log_file = self._get_current_file()
        fd = os.open(
            str(log_file),
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o600,
        )
        try:
            os.write(fd, line.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)

    @staticmethod
    def _redact_details(details: dict[str, Any]) -> dict[str, Any]:
        """Redact string values in the details dict."""
        redacted: dict[str, Any] = {}
        for key, value in details.items():
            if isinstance(value, str):
                redacted[key] = redact_text(value)
            elif isinstance(value, dict):
                redacted[key] = AuditLogger._redact_details(value)
            else:
                redacted[key] = value
        return redacted
