"""Tests for pnlclaw_core.infra.dedupe."""

import time

from pnlclaw_core.infra.dedupe import Deduplicator


class TestDeduplicator:
    def test_first_seen_not_duplicate(self):
        d = Deduplicator(ttl_seconds=10)
        assert d.is_duplicate("key1") is False

    def test_second_seen_is_duplicate(self):
        d = Deduplicator(ttl_seconds=10)
        d.is_duplicate("key1")
        assert d.is_duplicate("key1") is True

    def test_different_keys_not_duplicates(self):
        d = Deduplicator(ttl_seconds=10)
        d.is_duplicate("key1")
        assert d.is_duplicate("key2") is False

    def test_ttl_expiry(self):
        d = Deduplicator(ttl_seconds=0.05)
        d.is_duplicate("key1")
        time.sleep(0.1)
        assert d.is_duplicate("key1") is False  # Expired

    def test_max_size_eviction(self):
        d = Deduplicator(ttl_seconds=60, max_size=3)
        d.is_duplicate("a")
        d.is_duplicate("b")
        d.is_duplicate("c")
        d.is_duplicate("d")  # Should evict oldest
        assert d.size <= 3

    def test_clear(self):
        d = Deduplicator()
        d.is_duplicate("key1")
        d.clear()
        assert d.size == 0
        assert d.is_duplicate("key1") is False
