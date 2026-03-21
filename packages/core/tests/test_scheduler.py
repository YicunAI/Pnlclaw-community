"""Tests for pnlclaw_core.scheduler."""

from datetime import datetime, timedelta

import pytest

from pnlclaw_core.scheduler.schedule import Schedule, ScheduleType, _parse_interval
from pnlclaw_core.scheduler.service import SchedulerService
from pnlclaw_core.scheduler.store import SchedulerStore


class TestSchedule:
    def test_every_interval(self):
        s = Schedule(ScheduleType.EVERY, "5m", "cleanup")
        now = datetime(2025, 1, 1, 12, 0, 0)
        nxt = s.next_run(after=now)
        assert nxt == now + timedelta(minutes=5)

    def test_at_future(self):
        s = Schedule(ScheduleType.AT, "2099-01-01T00:00:00", "future_task")
        nxt = s.next_run()
        assert nxt is not None

    def test_at_past_returns_none(self):
        s = Schedule(ScheduleType.AT, "2000-01-01T00:00:00", "past_task")
        nxt = s.next_run()
        assert nxt is None

    def test_cron_returns_next_minute(self):
        s = Schedule(ScheduleType.CRON, "* * * * *", "every_min")
        now = datetime(2025, 1, 1, 12, 30, 15)
        nxt = s.next_run(after=now)
        assert nxt == datetime(2025, 1, 1, 12, 31, 0)


class TestParseInterval:
    def test_seconds(self):
        assert _parse_interval("30s") == timedelta(seconds=30)

    def test_minutes(self):
        assert _parse_interval("5m") == timedelta(minutes=5)

    def test_hours(self):
        assert _parse_interval("1h") == timedelta(hours=1)

    def test_days(self):
        assert _parse_interval("7d") == timedelta(days=7)

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            _parse_interval("abc")


class TestSchedulerStore:
    def test_log_and_read(self, tmp_path):
        store = SchedulerStore(tmp_path / "runs.jsonl")
        now = datetime.now()
        store.log_run("task1", now, now, "success")
        store.log_run("task2", now, now, "error", error="boom")
        records = store.read_log()
        assert len(records) == 2
        assert records[0]["task_name"] == "task1"
        assert records[1]["error"] == "boom"

    def test_empty_log(self, tmp_path):
        store = SchedulerStore(tmp_path / "empty.jsonl")
        assert store.read_log() == []


class TestSchedulerService:
    @pytest.mark.asyncio
    async def test_add_and_execute(self, tmp_path):
        store = SchedulerStore(tmp_path / "runs.jsonl")
        svc = SchedulerService(store)

        executed = []

        async def task():
            executed.append(1)

        svc.add(Schedule(ScheduleType.EVERY, "1s", "test"), task)
        await svc.run_once()
        assert len(executed) == 1

        # Check log
        records = store.read_log()
        assert records[0]["status"] == "success"

    @pytest.mark.asyncio
    async def test_failed_task_logged(self, tmp_path):
        store = SchedulerStore(tmp_path / "runs.jsonl")
        svc = SchedulerService(store)

        async def bad_task():
            raise ValueError("oops")

        svc.add(Schedule(ScheduleType.EVERY, "1s", "bad"), bad_task)
        await svc.run_once()
        records = store.read_log()
        assert records[0]["status"] == "error"
        assert "oops" in records[0]["error"]

    def test_task_names(self, tmp_path):
        store = SchedulerStore(tmp_path / "runs.jsonl")
        svc = SchedulerService(store)
        svc.add(Schedule(ScheduleType.EVERY, "1m", "a"), lambda: None)
        svc.add(Schedule(ScheduleType.EVERY, "5m", "b"), lambda: None)
        assert set(svc.task_names) == {"a", "b"}

    def test_remove(self, tmp_path):
        store = SchedulerStore(tmp_path / "runs.jsonl")
        svc = SchedulerService(store)
        svc.add(Schedule(ScheduleType.EVERY, "1m", "a"), lambda: None)
        svc.remove("a")
        assert svc.task_names == []
