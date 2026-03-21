"""Scheduler service: manage and execute scheduled tasks."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

from pnlclaw_core.scheduler.schedule import Schedule, ScheduleType
from pnlclaw_core.scheduler.store import SchedulerStore

logger = logging.getLogger(__name__)

TaskFn = Callable[[], Awaitable[None]]


class SchedulerService:
    """Manages scheduled tasks with isolated execution and failure logging.

    Args:
        store: SchedulerStore for persisting run logs.
    """

    def __init__(self, store: SchedulerStore) -> None:
        self._store = store
        self._tasks: dict[str, tuple[Schedule, TaskFn]] = {}
        self._running = False
        self._task: asyncio.Task[None] | None = None

    def add(self, schedule: Schedule, fn: TaskFn) -> None:
        """Register a scheduled task."""
        self._tasks[schedule.task_name] = (schedule, fn)

    def remove(self, task_name: str) -> None:
        """Remove a scheduled task."""
        self._tasks.pop(task_name, None)

    async def run_once(self) -> None:
        """Execute all tasks that are due. Called by the run loop or manually."""
        now = datetime.now()
        for name, (schedule, fn) in list(self._tasks.items()):
            next_run = schedule.next_run(after=now)
            if next_run is None:
                continue
            if schedule.schedule_type == ScheduleType.AT and next_run <= now:
                continue

            # For EVERY/CRON, we always execute in run_once (the loop handles timing)
            if schedule.schedule_type in (ScheduleType.EVERY, ScheduleType.CRON):
                await self._execute(name, fn)

    async def _execute(self, name: str, fn: TaskFn) -> None:
        """Execute a single task with isolation and logging."""
        started = datetime.now()
        try:
            await fn()
            finished = datetime.now()
            self._store.log_run(name, started, finished, status="success")
        except Exception as exc:
            finished = datetime.now()
            self._store.log_run(name, started, finished, status="error", error=str(exc))
            logger.warning("Scheduled task %s failed: %s", name, exc)

    async def start(self, interval: float = 60.0) -> None:
        """Start the scheduler loop.

        Args:
            interval: Seconds between each run_once cycle.
        """
        self._running = True
        while self._running:
            await self.run_once()
            await asyncio.sleep(interval)

    def stop(self) -> None:
        """Signal the scheduler loop to stop."""
        self._running = False

    @property
    def task_names(self) -> list[str]:
        """List registered task names."""
        return list(self._tasks.keys())
