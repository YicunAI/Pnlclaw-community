"""Tests for pnlclaw_security.audit."""

import json
import time
from pathlib import Path

from pnlclaw_security.audit import (
    AuditEvent,
    AuditEventType,
    AuditLogger,
    AuditSeverity,
)

# ---------------------------------------------------------------------------
# AuditEvent model
# ---------------------------------------------------------------------------


class TestAuditEvent:
    def test_defaults(self) -> None:
        event = AuditEvent(
            event_type=AuditEventType.TOOL_CALL,
            actor="user",
            action="market_ticker",
        )
        assert event.id  # UUID generated
        assert event.timestamp > 0
        assert event.severity == AuditSeverity.INFO
        assert event.outcome == "allowed"

    def test_json_serialization(self) -> None:
        event = AuditEvent(
            event_type=AuditEventType.TOOL_BLOCKED,
            severity=AuditSeverity.WARN,
            actor="agent",
            action="shell_exec",
            outcome="blocked",
        )
        data = json.loads(event.model_dump_json())
        assert data["event_type"] == "tool_blocked"
        assert data["severity"] == "warn"


# ---------------------------------------------------------------------------
# AuditLogger — basic logging
# ---------------------------------------------------------------------------


class TestAuditLogger:
    def test_log_creates_file(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path)
        event = AuditEvent(
            event_type=AuditEventType.TOOL_CALL,
            actor="user",
            action="market_ticker",
        )
        logger.log(event)

        files = list(tmp_path.glob("audit-*.jsonl"))
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8").strip()
        record = json.loads(content)
        assert record["event_type"] == "tool_call"
        assert record["actor"] == "user"

    def test_multiple_logs_append(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path)
        for i in range(5):
            logger.log(
                AuditEvent(
                    event_type=AuditEventType.TOOL_CALL,
                    actor="user",
                    action=f"action_{i}",
                )
            )

        files = list(tmp_path.glob("audit-*.jsonl"))
        assert len(files) == 1
        lines = files[0].read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 5


# ---------------------------------------------------------------------------
# Redaction of details
# ---------------------------------------------------------------------------


class TestAuditRedaction:
    def test_secrets_redacted_in_details(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path)
        event = AuditEvent(
            event_type=AuditEventType.SECRET_ACCESS,
            actor="system",
            action="resolve_secret",
            details={"key": "sk-abc123def456ghi789jkl012mno345"},
        )
        logger.log(event)

        files = list(tmp_path.glob("audit-*.jsonl"))
        content = files[0].read_text(encoding="utf-8").strip()
        record = json.loads(content)
        # The sk- prefixed key should be redacted
        assert "sk-abc123def456ghi789jkl012mno345" not in record["details"]["key"]

    def test_nested_dict_redacted(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path)
        event = AuditEvent(
            event_type=AuditEventType.CONFIG_CHANGE,
            actor="user",
            action="update_config",
            details={"config": {"api_key": "sk-nested_secret_key_value_long"}},
        )
        logger.log(event)

        files = list(tmp_path.glob("audit-*.jsonl"))
        content = files[0].read_text(encoding="utf-8").strip()
        record = json.loads(content)
        assert "sk-nested_secret_key_value_long" not in json.dumps(record)


# ---------------------------------------------------------------------------
# File rotation
# ---------------------------------------------------------------------------


class TestAuditRotation:
    def test_rotation_on_size_limit(self, tmp_path: Path) -> None:
        # Set very small max file size to trigger rotation
        logger = AuditLogger(log_dir=tmp_path, max_file_size=500)
        for i in range(20):
            logger.log(
                AuditEvent(
                    event_type=AuditEventType.TOOL_CALL,
                    actor="user",
                    action=f"action_{i}_with_some_padding_to_fill_space",
                )
            )

        files = list(tmp_path.glob("audit-*.jsonl"))
        assert len(files) >= 2


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


class TestAuditQuery:
    def test_query_all(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path)
        for i in range(3):
            logger.log(
                AuditEvent(
                    event_type=AuditEventType.TOOL_CALL,
                    actor="user",
                    action=f"action_{i}",
                )
            )

        events = logger.query()
        assert len(events) == 3

    def test_query_by_type(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path)
        logger.log(
            AuditEvent(
                event_type=AuditEventType.TOOL_CALL,
                actor="user",
                action="allowed",
            )
        )
        logger.log(
            AuditEvent(
                event_type=AuditEventType.TOOL_BLOCKED,
                actor="agent",
                action="blocked",
            )
        )

        events = logger.query(event_type=AuditEventType.TOOL_BLOCKED)
        assert len(events) == 1
        assert events[0].event_type == AuditEventType.TOOL_BLOCKED

    def test_query_with_limit(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path)
        for i in range(10):
            logger.log(
                AuditEvent(
                    event_type=AuditEventType.TOOL_CALL,
                    actor="user",
                    action=f"action_{i}",
                )
            )

        events = logger.query(limit=3)
        assert len(events) == 3

    def test_query_since(self, tmp_path: Path) -> None:
        logger = AuditLogger(log_dir=tmp_path)
        logger.log(
            AuditEvent(
                event_type=AuditEventType.TOOL_CALL,
                actor="user",
                action="old",
                timestamp=1000.0,
            )
        )
        logger.log(
            AuditEvent(
                event_type=AuditEventType.TOOL_CALL,
                actor="user",
                action="new",
                timestamp=time.time(),
            )
        )

        events = logger.query(since=time.time() - 60)
        assert len(events) == 1
        assert events[0].action == "new"
