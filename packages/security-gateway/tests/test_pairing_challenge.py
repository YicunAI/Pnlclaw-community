"""Tests for pnlclaw_security.pairing.challenge."""

from pathlib import Path

from pnlclaw_security.pairing.challenge import PairingChallenge
from pnlclaw_security.pairing.store import PairingStore


class TestVerifyCode:
    def test_successful_verification(self, tmp_path: Path) -> None:
        store = PairingStore(store_dir=tmp_path)
        req = store.create_request(device_info={"name": "phone"})
        challenge = PairingChallenge(store)

        result = challenge.verify_code(req.code)
        assert result.success is True
        assert result.device_info == {"name": "phone"}
        assert result.error is None

    def test_wrong_code_fails(self, tmp_path: Path) -> None:
        store = PairingStore(store_dir=tmp_path)
        store.create_request()
        challenge = PairingChallenge(store)

        result = challenge.verify_code("ZZZZZZZZ")
        assert result.success is False
        assert result.error is not None

    def test_code_consumed_after_use(self, tmp_path: Path) -> None:
        store = PairingStore(store_dir=tmp_path)
        req = store.create_request()
        challenge = PairingChallenge(store)

        # First use succeeds
        r1 = challenge.verify_code(req.code)
        assert r1.success is True

        # Second use fails (code consumed)
        r2 = challenge.verify_code(req.code)
        assert r2.success is False

    def test_case_insensitive(self, tmp_path: Path) -> None:
        store = PairingStore(store_dir=tmp_path)
        req = store.create_request()
        challenge = PairingChallenge(store)

        result = challenge.verify_code(req.code.lower())
        assert result.success is True

    def test_whitespace_stripped(self, tmp_path: Path) -> None:
        store = PairingStore(store_dir=tmp_path)
        req = store.create_request()
        challenge = PairingChallenge(store)

        result = challenge.verify_code(f"  {req.code}  ")
        assert result.success is True

    def test_expired_code_fails(self, tmp_path: Path) -> None:
        import time

        store = PairingStore(store_dir=tmp_path, ttl_seconds=1)
        req = store.create_request()
        challenge = PairingChallenge(store)

        time.sleep(1.1)
        result = challenge.verify_code(req.code)
        assert result.success is False

    def test_generic_error_message(self, tmp_path: Path) -> None:
        """Error messages must not distinguish 'not found' from 'expired'."""
        store = PairingStore(store_dir=tmp_path)
        challenge = PairingChallenge(store)

        # No codes exist
        r1 = challenge.verify_code("AAAAAAAA")

        # With expired code
        import time

        store2 = PairingStore(store_dir=tmp_path, ttl_seconds=1)
        store2.create_request()
        time.sleep(1.1)
        r2 = challenge.verify_code("AAAAAAAA")

        # Both should have the same error message
        assert r1.error == r2.error

    def test_empty_store(self, tmp_path: Path) -> None:
        store = PairingStore(store_dir=tmp_path)
        challenge = PairingChallenge(store)

        result = challenge.verify_code("ABCD1234")
        assert result.success is False
