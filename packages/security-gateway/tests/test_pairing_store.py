"""Tests for pnlclaw_security.pairing.store."""

import time
from pathlib import Path

from pnlclaw_security.pairing.store import (
    CODE_LENGTH,
    MAX_PENDING,
    UNAMBIGUOUS_ALPHABET,
    PairingStore,
)


class TestCodeGeneration:
    def test_code_length(self, tmp_path: Path) -> None:
        store = PairingStore(store_dir=tmp_path)
        code = store.generate_code()
        assert len(code) == CODE_LENGTH

    def test_code_alphabet(self, tmp_path: Path) -> None:
        store = PairingStore(store_dir=tmp_path)
        for _ in range(100):
            code = store.generate_code()
            for ch in code:
                assert ch in UNAMBIGUOUS_ALPHABET

    def test_no_ambiguous_chars(self, tmp_path: Path) -> None:
        store = PairingStore(store_dir=tmp_path)
        # 0, O, 1, I are excluded from the alphabet
        excluded = set("0O1I")
        for _ in range(100):
            code = store.generate_code()
            assert not excluded.intersection(code)


class TestCreateRequest:
    def test_creates_request(self, tmp_path: Path) -> None:
        store = PairingStore(store_dir=tmp_path)
        req = store.create_request(device_info={"name": "test-device"})
        assert len(req.code) == CODE_LENGTH
        assert req.expires_at > req.created_at
        assert req.device_info == {"name": "test-device"}

    def test_max_pending_enforced(self, tmp_path: Path) -> None:
        store = PairingStore(store_dir=tmp_path)
        for _ in range(MAX_PENDING + 2):
            store.create_request()

        pending = store.get_pending()
        assert len(pending) <= MAX_PENDING

    def test_unique_codes(self, tmp_path: Path) -> None:
        store = PairingStore(store_dir=tmp_path)
        codes = set()
        for _ in range(MAX_PENDING):
            req = store.create_request()
            codes.add(req.code)
        assert len(codes) == MAX_PENDING


class TestTTLExpiration:
    def test_expired_requests_purged(self, tmp_path: Path) -> None:
        store = PairingStore(store_dir=tmp_path, ttl_seconds=1)
        store.create_request()
        assert len(store.get_pending()) == 1

        # Simulate expiration
        time.sleep(1.1)
        assert len(store.get_pending()) == 0


class TestRemoveRequest:
    def test_remove_existing(self, tmp_path: Path) -> None:
        store = PairingStore(store_dir=tmp_path)
        req = store.create_request()
        assert store.remove_request(req.code) is True
        assert len(store.get_pending()) == 0

    def test_remove_nonexistent(self, tmp_path: Path) -> None:
        store = PairingStore(store_dir=tmp_path)
        assert store.remove_request("ZZZZZZZZ") is False

    def test_remove_case_insensitive(self, tmp_path: Path) -> None:
        store = PairingStore(store_dir=tmp_path)
        req = store.create_request()
        assert store.remove_request(req.code.lower()) is True


class TestPersistence:
    def test_save_and_load(self, tmp_path: Path) -> None:
        store1 = PairingStore(store_dir=tmp_path)
        req = store1.create_request(device_info={"type": "desktop"})

        # Create new store instance to test persistence
        store2 = PairingStore(store_dir=tmp_path)
        pending = store2.get_pending()
        assert len(pending) == 1
        assert pending[0].code == req.code
        assert pending[0].device_info == {"type": "desktop"}

    def test_corrupt_file_handled(self, tmp_path: Path) -> None:
        store_file = tmp_path / "pending.json"
        store_file.write_text("not valid json")

        store = PairingStore(store_dir=tmp_path)
        assert store.get_pending() == []
