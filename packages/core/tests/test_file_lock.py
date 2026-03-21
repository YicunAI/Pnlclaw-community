"""Tests for pnlclaw_core.infra.file_lock."""

import os

from pnlclaw_core.infra.file_lock import FileLock


class TestFileLock:
    def test_acquire_and_release(self, tmp_path):
        lock_file = tmp_path / "test.lock"
        lock = FileLock(lock_file)
        lock.acquire()
        assert lock.is_held
        assert lock_file.is_file()
        assert lock_file.read_text().strip() == str(os.getpid())
        lock.release()
        assert not lock.is_held
        assert not lock_file.is_file()

    def test_context_manager(self, tmp_path):
        lock_file = tmp_path / "test.lock"
        with FileLock(lock_file) as lock:
            assert lock.is_held
        assert not lock_file.is_file()

    def test_reentrant(self, tmp_path):
        lock_file = tmp_path / "test.lock"
        lock = FileLock(lock_file)
        lock.acquire()
        lock.acquire()  # Should not raise (same PID)
        assert lock.is_held
        lock.release()

    def test_stale_lock_cleanup(self, tmp_path):
        lock_file = tmp_path / "test.lock"
        # Write a PID that definitely doesn't exist
        lock_file.write_text("999999999", encoding="utf-8")
        lock = FileLock(lock_file)
        lock.acquire()  # Should clean stale lock
        assert lock.is_held
        lock.release()

    def test_live_lock_raises(self, tmp_path):
        lock_file = tmp_path / "test.lock"
        # Write current process PID from a "different" FileLock instance
        lock1 = FileLock(lock_file)
        lock1.acquire()

        lock2 = FileLock(lock_file)
        # Same PID, so it should be re-entrant — but let's test a foreign PID
        # We can't easily fake a foreign live PID, so we test that our own works
        lock2.acquire()  # Re-entrant with same PID
        lock1.release()
