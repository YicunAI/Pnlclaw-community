"""Process-level file lock with PID-based stale lock detection."""

from __future__ import annotations

import os
from pathlib import Path


class FileLockError(Exception):
    """Raised when the lock cannot be acquired."""


class FileLock:
    """File-based process lock with PID staleness detection.

    Creates a lock file containing the PID. If a lock file exists but
    the owning process is dead, the stale lock is cleaned up automatically.

    Args:
        path: Path to the lock file.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._held = False

    def acquire(self) -> None:
        """Acquire the lock, cleaning up stale locks.

        Raises:
            FileLockError: If the lock is held by a live process.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)

        if self._path.is_file():
            existing_pid = self._read_pid()
            if existing_pid is not None:
                if existing_pid == os.getpid():
                    # Re-entrant: we already hold it
                    self._held = True
                    return
                if self._is_process_alive(existing_pid):
                    raise FileLockError(f"Lock held by PID {existing_pid}: {self._path}")
            # Stale lock — clean up
            self._path.unlink(missing_ok=True)

        self._path.write_text(str(os.getpid()), encoding="utf-8")
        self._held = True

    def release(self) -> None:
        """Release the lock if we hold it."""
        if self._held and self._path.is_file():
            pid = self._read_pid()
            if pid == os.getpid():
                self._path.unlink(missing_ok=True)
        self._held = False

    @property
    def is_held(self) -> bool:
        """Whether this instance currently holds the lock."""
        return self._held

    def _read_pid(self) -> int | None:
        """Read PID from lock file, returning None if unreadable."""
        try:
            return int(self._path.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            return None

    @staticmethod
    def _is_process_alive(pid: int) -> bool:
        """Check if a process with the given PID is alive."""
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def __enter__(self) -> FileLock:
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()
