"""Tests for pnlclaw_types.events — serialization/deserialization roundtrips."""

from pnlclaw_types.events import DiagnosticEvent, DiagnosticLevel, HookEvent


class TestDiagnosticEvent:
    def test_roundtrip(self):
        e = DiagnosticEvent(
            sequence_id=1,
            timestamp=1711000000000,
            category="market",
            level=DiagnosticLevel.INFO,
            message="WebSocket connected",
            data={"exchange": "binance"},
        )
        raw = e.model_dump_json()
        restored = DiagnosticEvent.model_validate_json(raw)
        assert restored == e

    def test_has_sequence_id_and_timestamp(self):
        """Spec: events must have sequence_id + timestamp."""
        fields = set(DiagnosticEvent.model_fields.keys())
        assert {"sequence_id", "timestamp"}.issubset(fields)

    def test_data_optional(self):
        e = DiagnosticEvent(
            sequence_id=0,
            timestamp=1711000000000,
            category="system",
            level=DiagnosticLevel.DEBUG,
            message="Startup",
        )
        assert e.data is None

    def test_levels(self):
        expected = {"debug", "info", "warning", "error", "critical"}
        actual = {level.value for level in DiagnosticLevel}
        assert actual == expected


class TestHookEvent:
    def test_roundtrip(self):
        e = HookEvent(
            sequence_id=42,
            timestamp=1711000000000,
            hook_name="on_order_placed",
            payload={"order_id": "ord-001", "symbol": "BTC/USDT"},
        )
        raw = e.model_dump_json()
        restored = HookEvent.model_validate_json(raw)
        assert restored == e

    def test_has_sequence_id_and_timestamp(self):
        """Spec: events must have sequence_id + timestamp."""
        fields = set(HookEvent.model_fields.keys())
        assert {"sequence_id", "timestamp"}.issubset(fields)

    def test_empty_payload(self):
        e = HookEvent(
            sequence_id=0,
            timestamp=1711000000000,
            hook_name="on_startup",
        )
        assert e.payload == {}
