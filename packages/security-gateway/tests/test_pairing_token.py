"""Tests for pnlclaw_security.pairing.token."""

import time
from pathlib import Path

from pnlclaw_security.pairing.token import TokenStore


class TestIssueToken:
    def test_issue_creates_token(self, tmp_path: Path) -> None:
        store = TokenStore(store_dir=tmp_path)
        token = store.issue_token("device-1")
        assert token.token  # non-empty
        assert token.device_id == "device-1"
        assert token.expires_at > token.created_at
        assert "read" in token.scopes

    def test_issue_with_custom_scopes(self, tmp_path: Path) -> None:
        store = TokenStore(store_dir=tmp_path)
        token = store.issue_token("device-1", scopes=["read", "write"])
        assert token.scopes == ["read", "write"]

    def test_issue_replaces_existing(self, tmp_path: Path) -> None:
        store = TokenStore(store_dir=tmp_path)
        t1 = store.issue_token("device-1")
        t2 = store.issue_token("device-1")
        assert t1.token != t2.token
        # Only one token for this device
        assert store.validate_token(t1.token) is None
        assert store.validate_token(t2.token) is not None

    def test_unique_tokens(self, tmp_path: Path) -> None:
        store = TokenStore(store_dir=tmp_path)
        tokens = {store.issue_token(f"dev-{i}").token for i in range(10)}
        assert len(tokens) == 10


class TestValidateToken:
    def test_valid_token(self, tmp_path: Path) -> None:
        store = TokenStore(store_dir=tmp_path)
        issued = store.issue_token("device-1")
        result = store.validate_token(issued.token)
        assert result is not None
        assert result.device_id == "device-1"

    def test_invalid_token(self, tmp_path: Path) -> None:
        store = TokenStore(store_dir=tmp_path)
        store.issue_token("device-1")
        assert store.validate_token("not-a-valid-token") is None

    def test_expired_token(self, tmp_path: Path) -> None:
        store = TokenStore(store_dir=tmp_path)
        issued = store.issue_token("device-1", ttl_seconds=1)
        time.sleep(1.1)
        assert store.validate_token(issued.token) is None

    def test_empty_store(self, tmp_path: Path) -> None:
        store = TokenStore(store_dir=tmp_path)
        assert store.validate_token("any-token") is None


class TestRevokeToken:
    def test_revoke_existing(self, tmp_path: Path) -> None:
        store = TokenStore(store_dir=tmp_path)
        issued = store.issue_token("device-1")
        assert store.revoke_token("device-1") is True
        assert store.validate_token(issued.token) is None

    def test_revoke_nonexistent(self, tmp_path: Path) -> None:
        store = TokenStore(store_dir=tmp_path)
        assert store.revoke_token("no-such-device") is False

    def test_revoke_all(self, tmp_path: Path) -> None:
        store = TokenStore(store_dir=tmp_path)
        for i in range(3):
            store.issue_token(f"device-{i}")
        count = store.revoke_all()
        assert count == 3
        for i in range(3):
            assert store.validate_token(f"device-{i}") is None


class TestPersistence:
    def test_save_and_load(self, tmp_path: Path) -> None:
        store1 = TokenStore(store_dir=tmp_path)
        issued = store1.issue_token("device-1", scopes=["read", "trade"])

        store2 = TokenStore(store_dir=tmp_path)
        result = store2.validate_token(issued.token)
        assert result is not None
        assert result.scopes == ["read", "trade"]
