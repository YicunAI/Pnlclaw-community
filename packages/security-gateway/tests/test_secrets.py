"""Tests for pnlclaw_security.secrets."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pnlclaw_security.secrets import (
    ResolvedSecret,
    SecretManager,
    SecretRef,
    SecretResolutionError,
    SecretSource,
)

# ---------------------------------------------------------------------------
# ResolvedSecret safety
# ---------------------------------------------------------------------------


class TestResolvedSecretSafety:
    def test_repr_never_leaks_value(self) -> None:
        secret = ResolvedSecret(
            value="super-secret-key",
            source=SecretSource.ENV,
            ref=SecretRef(source=SecretSource.ENV, id="TEST_KEY"),
        )
        assert "super-secret-key" not in repr(secret)
        assert "redacted" in repr(secret)

    def test_str_never_leaks_value(self) -> None:
        secret = ResolvedSecret(
            value="super-secret-key",
            source=SecretSource.ENV,
            ref=SecretRef(source=SecretSource.ENV, id="TEST_KEY"),
        )
        assert str(secret) == "***"

    def test_use_returns_value(self) -> None:
        secret = ResolvedSecret(
            value="my-api-key",
            source=SecretSource.ENV,
            ref=SecretRef(source=SecretSource.ENV, id="KEY"),
        )
        assert secret.use() == "my-api-key"

    def test_format_string_safety(self) -> None:
        secret = ResolvedSecret(
            value="leaked-value",
            source=SecretSource.ENV,
            ref=SecretRef(source=SecretSource.ENV, id="KEY"),
        )
        # Common accident: f-string with secret
        formatted = f"Key is {secret}"
        assert "leaked-value" not in formatted
        assert "***" in formatted


# ---------------------------------------------------------------------------
# SecretManager — env resolution
# ---------------------------------------------------------------------------


class TestSecretManagerEnv:
    @pytest.mark.asyncio
    async def test_resolve_env_var(self) -> None:
        manager = SecretManager()
        ref = SecretRef(source=SecretSource.ENV, id="TEST_SECRET_VAR")
        with patch.dict(os.environ, {"TEST_SECRET_VAR": "test-value"}):
            resolved = await manager.resolve(ref)
            assert resolved.use() == "test-value"
            assert resolved.source == SecretSource.ENV

    @pytest.mark.asyncio
    async def test_missing_env_var_raises(self) -> None:
        manager = SecretManager()
        ref = SecretRef(source=SecretSource.ENV, id="NONEXISTENT_VAR_12345")
        with pytest.raises(SecretResolutionError, match="not found"):
            await manager.resolve(ref)


# ---------------------------------------------------------------------------
# SecretManager — file resolution
# ---------------------------------------------------------------------------


class TestSecretManagerFile:
    @pytest.mark.asyncio
    async def test_resolve_file(self, tmp_path: Path) -> None:
        secret_dir = tmp_path / "secrets"
        secret_dir.mkdir()
        secret_file = secret_dir / "my_key"
        secret_file.write_text("file-secret-value\n")
        if sys.platform != "win32":
            secret_file.chmod(0o600)

        manager = SecretManager(base_dir=secret_dir)
        ref = SecretRef(source=SecretSource.FILE, id="my_key")
        resolved = await manager.resolve(ref)
        assert resolved.use() == "file-secret-value"

    @pytest.mark.asyncio
    async def test_resolve_file_with_provider(self, tmp_path: Path) -> None:
        secret_dir = tmp_path / "secrets"
        provider_dir = secret_dir / "exchange"
        provider_dir.mkdir(parents=True)
        secret_file = provider_dir / "api_key"
        secret_file.write_text("exchange-key")
        if sys.platform != "win32":
            secret_file.chmod(0o600)

        manager = SecretManager(base_dir=secret_dir)
        ref = SecretRef(source=SecretSource.FILE, provider="exchange", id="api_key")
        resolved = await manager.resolve(ref)
        assert resolved.use() == "exchange-key"

    @pytest.mark.asyncio
    async def test_missing_file_raises(self, tmp_path: Path) -> None:
        manager = SecretManager(base_dir=tmp_path)
        ref = SecretRef(source=SecretSource.FILE, id="nonexistent")
        with pytest.raises(SecretResolutionError, match="not found"):
            await manager.resolve(ref)

    @pytest.mark.asyncio
    async def test_oversized_file_raises(self, tmp_path: Path) -> None:
        big_file = tmp_path / "big_secret"
        big_file.write_text("x" * 2_000_000)
        if sys.platform != "win32":
            big_file.chmod(0o600)

        manager = SecretManager(base_dir=tmp_path)
        ref = SecretRef(source=SecretSource.FILE, id="big_secret")
        with pytest.raises(SecretResolutionError, match="exceeds"):
            await manager.resolve(ref)

    @pytest.mark.asyncio
    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
    async def test_world_readable_file_raises(self, tmp_path: Path) -> None:
        secret_file = tmp_path / "bad_perms"
        secret_file.write_text("secret")
        secret_file.chmod(0o644)  # World-readable

        manager = SecretManager(base_dir=tmp_path)
        ref = SecretRef(source=SecretSource.FILE, id="bad_perms")
        with pytest.raises(SecretResolutionError, match="readable by group"):
            await manager.resolve(ref)


# ---------------------------------------------------------------------------
# SecretManager — keyring resolution
# ---------------------------------------------------------------------------


class TestSecretManagerKeyring:
    @pytest.mark.asyncio
    async def test_resolve_keyring(self) -> None:
        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = "keyring-secret"

        manager = SecretManager()
        ref = SecretRef(source=SecretSource.KEYRING, provider="pnlclaw", id="api_key")

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            resolved = await manager.resolve(ref)
            assert resolved.use() == "keyring-secret"
            mock_keyring.get_password.assert_called_once_with("pnlclaw", "api_key")

    @pytest.mark.asyncio
    async def test_keyring_not_installed(self) -> None:
        manager = SecretManager()
        ref = SecretRef(source=SecretSource.KEYRING, provider="pnlclaw", id="key")

        with patch.dict("sys.modules", {"keyring": None}):
            with pytest.raises(SecretResolutionError, match="keyring library not installed"):
                await manager.resolve(ref)

    @pytest.mark.asyncio
    async def test_keyring_entry_not_found(self) -> None:
        mock_keyring = MagicMock()
        mock_keyring.get_password.return_value = None

        manager = SecretManager()
        ref = SecretRef(source=SecretSource.KEYRING, provider="pnlclaw", id="missing")

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            with pytest.raises(SecretResolutionError, match="No keyring entry"):
                await manager.resolve(ref)


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------


class TestSecretManagerStoreDelete:
    @pytest.mark.asyncio
    async def test_store_and_resolve_keyring_roundtrip(self) -> None:
        mock_keyring = MagicMock()
        values: dict[tuple[str, str], str] = {}

        def _set_password(service: str, key: str, value: str) -> None:
            values[(service, key)] = value

        def _get_password(service: str, key: str) -> str | None:
            return values.get((service, key))

        def _delete_password(service: str, key: str) -> None:
            values.pop((service, key), None)

        mock_keyring.set_password.side_effect = _set_password
        mock_keyring.get_password.side_effect = _get_password
        mock_keyring.delete_password.side_effect = _delete_password

        manager = SecretManager()
        ref = SecretRef(source=SecretSource.KEYRING, provider="pnlclaw", id="llm_api_key")

        with patch.dict("sys.modules", {"keyring": mock_keyring}):
            await manager.store(ref, "sk-live-key")
            resolved = await manager.resolve(ref)
            assert resolved.use() == "sk-live-key"
            await manager.delete(ref)
            assert await manager.exists(ref) is False

    @pytest.mark.asyncio
    async def test_store_requires_keyring_by_default(self, tmp_path: Path) -> None:
        manager = SecretManager(base_dir=tmp_path)
        ref = SecretRef(source=SecretSource.FILE, id="fallback_key")

        with pytest.raises(SecretResolutionError, match="requires keyring backend"):
            await manager.store(ref, "value")

    @pytest.mark.asyncio
    async def test_store_file_allowed_when_policy_disabled(self, tmp_path: Path) -> None:
        manager = SecretManager(base_dir=tmp_path, keyring_required_for_store=False)
        ref = SecretRef(source=SecretSource.FILE, provider="exchange", id="api_key")

        await manager.store(ref, "file-value")
        resolved = await manager.resolve(ref)
        assert resolved.use() == "file-value"

        await manager.delete(ref)
        assert await manager.exists(ref) is False

    def test_keyring_available_false_without_dependency(self) -> None:
        manager = SecretManager()
        with patch.dict("sys.modules", {"keyring": None}):
            assert manager.keyring_available() is False


class TestSecretManagerCache:
    @pytest.mark.asyncio
    async def test_cache_hit(self) -> None:
        manager = SecretManager()
        ref = SecretRef(source=SecretSource.ENV, id="CACHE_TEST_VAR")

        with patch.dict(os.environ, {"CACHE_TEST_VAR": "cached-value"}):
            r1 = await manager.resolve(ref)
            r2 = await manager.resolve(ref)
            assert r1 is r2  # Same object from cache

    @pytest.mark.asyncio
    async def test_clear_cache(self) -> None:
        manager = SecretManager()
        ref = SecretRef(source=SecretSource.ENV, id="CLEAR_CACHE_VAR")

        with patch.dict(os.environ, {"CLEAR_CACHE_VAR": "v1"}):
            r1 = await manager.resolve(ref)

        manager.clear_cache()

        with patch.dict(os.environ, {"CLEAR_CACHE_VAR": "v2"}):
            r2 = await manager.resolve(ref)
            assert r2.use() == "v2"
            assert r1 is not r2
