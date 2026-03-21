"""Schedule model: supports at/every/cron scheduling patterns."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


class ScheduleType(str, Enum):
    """Schedule trigger type."""

    AT = "at"          # One-shot at a specific time
    EVERY = "every"    # Recurring interval
    CRON = "cron"      # Cron expression (simplified 5-field)


@dataclass
class Schedule:
    """A schedule definition.

    Args:
        schedule_type: AT, EVERY, or CRON.
        value: Meaning depends on type:
            - AT: ISO datetime string
            - EVERY: interval string like "5m", "1h", "30s"
            - CRON: 5-field cron expression "M H DoM Mon DoW"
        task_name: Human-readable task identifier.
    """

    schedule_type: ScheduleType
    value: str
    task_name: str

    def next_run(self, after: datetime | None = None) -> datetime | None:
        """Calculate the next run time after *after* (defaults to now).

        Returns None for AT schedules that are in the past.
        """
        if after is None:
            after = datetime.now()

        if self.schedule_type == ScheduleType.AT:
            target = datetime.fromisoformat(self.value)
            return target if target > after else None

        if self.schedule_type == ScheduleType.EVERY:
            delta = _parse_interval(self.value)
            return after + delta

        if self.schedule_type == ScheduleType.CRON:
            # Simplified: return next minute boundary for now
            # Full cron parsing is complex; this is MVP
            next_min = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
            return next_min

        return None


def _parse_interval(value: str) -> timedelta:
    """Parse an interval string like '5m', '1h', '30s' into a timedelta."""
    match = re.match(r"^(\d+)(s|m|h|d)$", value.strip())
    if not match:
        raise ValueError(f"Invalid interval format: {value!r} (expected e.g. '5m', '1h', '30s')")
    amount = int(match.group(1))
    unit = match.group(2)
    return {
        "s": timedelta(seconds=amount),
        "m": timedelta(minutes=amount),
        "h": timedelta(hours=amount),
        "d": timedelta(days=amount),
    }[unit]
