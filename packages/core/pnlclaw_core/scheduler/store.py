"""Scheduler store: JSONL append-only run log."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class SchedulerStore:
    """Append-only JSONL log for scheduler run records.

    Each run is a single JSON line with: task_name, started_at, finished_at,
    status, error.
    """

    def __init__(self, log_path: str | Path) -> None:
        self._path = Path(log_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def log_run(
        self,
        task_name: str,
        started_at: datetime,
        finished_at: datetime,
        status: str,
        error: str | None = None,
    ) -> None:
        """Append a run record to the JSONL log."""
        record: dict[str, Any] = {
            "task_name": task_name,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "status": status,
        }
        if error:
            record["error"] = error
        line = json.dumps(record) + "\n"
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(line)

    def read_log(self) -> list[dict[str, Any]]:
        """Read all run records from the log."""
        if not self._path.is_file():
            return []
        records: list[dict[str, Any]] = []
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records
