"""Tests for pnlclaw_core.diagnostics.events."""

from pnlclaw_core.diagnostics.events import DiagnosticBus, DiagnosticRecord


class TestDiagnosticBus:
    def test_subscribe_and_emit(self):
        bus = DiagnosticBus()
        received = []
        bus.subscribe("market", lambda e: received.append(e))
        event = DiagnosticRecord(category="market", message="tick")
        bus.emit(event)
        assert len(received) == 1
        assert received[0].message == "tick"

    def test_wildcard_subscriber(self):
        bus = DiagnosticBus()
        received = []
        bus.subscribe("*", lambda e: received.append(e))
        bus.emit(DiagnosticRecord(category="order", message="placed"))
        bus.emit(DiagnosticRecord(category="market", message="tick"))
        assert len(received) == 2

    def test_no_matching_handler(self):
        bus = DiagnosticBus()
        bus.emit(DiagnosticRecord(category="unknown", message="noop"))

    def test_handler_exception_does_not_crash(self):
        bus = DiagnosticBus()
        bus.subscribe("test", lambda e: 1 / 0)
        bus.emit(DiagnosticRecord(category="test", message="boom"))

    def test_recursion_protection(self):
        bus = DiagnosticBus()
        depth_reached = [0]

        def recursive_handler(e):
            depth_reached[0] += 1
            bus.emit(DiagnosticRecord(category="test", message="recurse"))

        bus.subscribe("test", recursive_handler)
        bus.emit(DiagnosticRecord(category="test", message="start"))
        assert depth_reached[0] == 100  # Capped at max depth

    def test_clear(self):
        bus = DiagnosticBus()
        received = []
        bus.subscribe("test", lambda e: received.append(e))
        bus.clear()
        bus.emit(DiagnosticRecord(category="test", message="after clear"))
        assert len(received) == 0
