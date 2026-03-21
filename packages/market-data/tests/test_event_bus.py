"""Tests for pnlclaw_market.event_bus — internal event bus."""

from __future__ import annotations

import asyncio

import pytest

from pnlclaw_market.event_bus import EventBus


class _DummyEvent:
    def __init__(self, value: int = 0) -> None:
        self.value = value


class _OtherEvent:
    pass


class TestEventBus:
    """Unit tests for the EventBus."""

    def test_sync_subscribe_and_publish(self) -> None:
        bus = EventBus()
        received: list[_DummyEvent] = []
        bus.subscribe(_DummyEvent, received.append)

        event = _DummyEvent(42)
        bus.publish(event)

        assert len(received) == 1
        assert received[0].value == 42

    def test_multiple_listeners(self) -> None:
        bus = EventBus()
        results_a: list[_DummyEvent] = []
        results_b: list[_DummyEvent] = []
        bus.subscribe(_DummyEvent, results_a.append)
        bus.subscribe(_DummyEvent, results_b.append)

        bus.publish(_DummyEvent(1))
        assert len(results_a) == 1
        assert len(results_b) == 1

    def test_type_isolation(self) -> None:
        bus = EventBus()
        dummy_received: list[_DummyEvent] = []
        other_received: list[_OtherEvent] = []
        bus.subscribe(_DummyEvent, dummy_received.append)
        bus.subscribe(_OtherEvent, other_received.append)

        bus.publish(_DummyEvent(1))
        assert len(dummy_received) == 1
        assert len(other_received) == 0

    def test_unsubscribe(self) -> None:
        bus = EventBus()
        received: list[_DummyEvent] = []
        bus.subscribe(_DummyEvent, received.append)
        bus.unsubscribe(_DummyEvent, received.append)

        bus.publish(_DummyEvent(1))
        assert len(received) == 0

    def test_unsubscribe_nonexistent_is_noop(self) -> None:
        bus = EventBus()
        bus.unsubscribe(_DummyEvent, lambda e: None)  # no error

    def test_handler_count(self) -> None:
        bus = EventBus()
        assert bus.handler_count(_DummyEvent) == 0
        bus.subscribe(_DummyEvent, lambda e: None)
        assert bus.handler_count(_DummyEvent) == 1

    def test_clear(self) -> None:
        bus = EventBus()
        bus.subscribe(_DummyEvent, lambda e: None)
        bus.clear()
        assert bus.handler_count(_DummyEvent) == 0

    def test_handler_exception_does_not_crash(self) -> None:
        bus = EventBus()
        received: list[_DummyEvent] = []

        def bad_handler(e: _DummyEvent) -> None:
            raise RuntimeError("boom")

        bus.subscribe(_DummyEvent, bad_handler)
        bus.subscribe(_DummyEvent, received.append)

        bus.publish(_DummyEvent(1))
        # Second handler still called despite first raising
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_async_publish(self) -> None:
        bus = EventBus()
        received: list[_DummyEvent] = []

        async def async_handler(e: _DummyEvent) -> None:
            received.append(e)

        bus.subscribe(_DummyEvent, async_handler)
        await bus.publish_async(_DummyEvent(99))
        assert len(received) == 1
        assert received[0].value == 99

    @pytest.mark.asyncio
    async def test_publish_schedules_async_handlers(self) -> None:
        bus = EventBus()
        received: list[int] = []

        async def async_handler(e: _DummyEvent) -> None:
            received.append(e.value)

        bus.subscribe(_DummyEvent, async_handler)
        bus.publish(_DummyEvent(7))
        # Give the scheduled task a chance to run
        await asyncio.sleep(0.05)
        assert 7 in received
