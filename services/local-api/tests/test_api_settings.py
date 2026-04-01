"""API tests for settings endpoints."""

from __future__ import annotations

import base64

import pytest
from app.core.crypto import ENCRYPTED_PREFIX, KeyPairManager
from app.core.dependencies import get_key_pair_manager, get_settings_service
from app.core.settings_service import SettingsService
from app.main import create_app
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from httpx import ASGITransport, AsyncClient
from pnlclaw_security.secrets import SecretResolutionError


class StubSecretManager:
    def __init__(self, keyring_available: bool = True) -> None:
        self._available = keyring_available
        self._store: dict[str, str] = {}

    def keyring_available(self) -> bool:
        return self._available

    async def exists(self, ref) -> bool:
        key = f"{ref.provider}:{ref.id}"
        return key in self._store

    async def resolve(self, ref):
        from pnlclaw_security.secrets import ResolvedSecret, SecretResolutionError, SecretSource
        key = f"{ref.provider}:{ref.id}"
        if key not in self._store:
            raise SecretResolutionError(f"not found: {key}")
        class _R:
            def use(self_):
                return self._store[key]
        return _R()

    async def store(self, ref, value: str) -> None:
        if not self._available:
            raise SecretResolutionError("keyring unavailable")
        self._store[f"{ref.provider}:{ref.id}"] = value

    async def delete(self, ref) -> None:
        self._store.pop(f"{ref.provider}:{ref.id}", None)


@pytest.mark.asyncio
async def test_get_settings_returns_masked_secret_state(tmp_path):
    app = create_app()
    service = SettingsService(
        config_path=tmp_path / "settings.json",
        secret_manager=StubSecretManager(),
    )
    app.dependency_overrides[get_settings_service] = lambda: service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/settings")

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["general"]["api_url"] == "http://localhost:8080"
    assert body["data"]["exchange"]["market_type"] == "spot"
    assert body["data"]["llm"]["api_key_configured"] is False
    assert "request_id" in body["meta"]


@pytest.mark.asyncio
async def test_put_settings_updates_and_masks(tmp_path):
    app = create_app()
    service = SettingsService(
        config_path=tmp_path / "settings.json",
        secret_manager=StubSecretManager(),
    )
    app.dependency_overrides[get_settings_service] = lambda: service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.put(
            "/api/v1/settings",
            json={
                "general": {"api_url": "http://127.0.0.1:8080"},
                "exchange": {
                    "provider": "okx",
                    "market_type": "futures",
                },
                "llm": {
                    "provider": "openai",
                    "api_key": "sk-test-secret",
                    "base_url": "https://api.openai.com/v1",
                    "model": "claude-opus-4-6",
                },
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["general"]["api_url"] == "http://127.0.0.1:8080"
    assert body["data"]["exchange"]["provider"] == "okx"
    assert body["data"]["exchange"]["market_type"] == "futures"
    assert body["data"]["llm"]["api_key_configured"] is True
    assert body["data"]["llm"]["api_key_masked"] == "••••••••"


@pytest.mark.asyncio
async def test_put_settings_clear_secret(tmp_path):
    app = create_app()
    secret_manager = StubSecretManager()
    service = SettingsService(
        config_path=tmp_path / "settings.json",
        secret_manager=secret_manager,
    )
    app.dependency_overrides[get_settings_service] = lambda: service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.put(
            "/api/v1/settings",
            json={"llm": {"api_key": "sk-test-secret"}},
        )
        resp = await c.put(
            "/api/v1/settings",
            json={"llm": {"clear_api_key": True}},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["llm"]["api_key_configured"] is False




@pytest.mark.asyncio
async def test_put_settings_invalid_exchange_values_rejected(tmp_path):
    app = create_app()
    service = SettingsService(
        config_path=tmp_path / "settings.json",
        secret_manager=StubSecretManager(),
    )
    app.dependency_overrides[get_settings_service] = lambda: service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.put(
            "/api/v1/settings",
            json={"exchange": {"provider": "bybit", "market_type": "perp"}},
        )

    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    app = create_app()
    service = SettingsService(
        config_path=tmp_path / "settings.json",
        secret_manager=StubSecretManager(keyring_available=False),
    )
    app.dependency_overrides[get_settings_service] = lambda: service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.put(
            "/api/v1/settings",
            json={"llm": {"api_key": "sk-test-secret"}},
        )

    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "SERVICE_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Public-key endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_public_key_returns_jwk(tmp_path):
    app = create_app()
    kpm = KeyPairManager()
    service = SettingsService(
        config_path=tmp_path / "settings.json",
        secret_manager=StubSecretManager(),
        key_pair_manager=kpm,
    )
    app.dependency_overrides[get_settings_service] = lambda: service
    app.dependency_overrides[get_key_pair_manager] = lambda: kpm

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/settings/public-key")

    assert resp.status_code == 200
    jwk = resp.json()["data"]
    assert jwk["kty"] == "RSA"
    assert jwk["alg"] == "RSA-OAEP-256"
    assert "n" in jwk
    assert "e" in jwk


# ---------------------------------------------------------------------------
# Encrypted secret round-trip
# ---------------------------------------------------------------------------


def _encrypt_with_manager(kpm: KeyPairManager, plaintext: str) -> str:
    """Simulate what the frontend does: RSA-OAEP encrypt and prefix."""
    pub = kpm._public_key  # noqa: SLF001
    ciphertext = pub.encrypt(
        plaintext.encode("utf-8"),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    b64 = base64.b64encode(ciphertext).decode("ascii")
    return f"{ENCRYPTED_PREFIX}{b64}"


@pytest.mark.asyncio
async def test_put_settings_encrypted_llm_key_round_trip(tmp_path):
    app = create_app()
    kpm = KeyPairManager()
    stub = StubSecretManager()
    service = SettingsService(
        config_path=tmp_path / "settings.json",
        secret_manager=stub,
        key_pair_manager=kpm,
    )
    app.dependency_overrides[get_settings_service] = lambda: service
    app.dependency_overrides[get_key_pair_manager] = lambda: kpm

    encrypted = _encrypt_with_manager(kpm, "sk-real-secret-key")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.put(
            "/api/v1/settings",
            json={"llm": {"api_key": encrypted}},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["llm"]["api_key_configured"] is True

    stored = stub._store.get("pnlclaw.llm:api_key")
    assert stored == "sk-real-secret-key"


@pytest.mark.asyncio
async def test_put_settings_encrypted_exchange_keys(tmp_path):
    app = create_app()
    kpm = KeyPairManager()
    stub = StubSecretManager()
    service = SettingsService(
        config_path=tmp_path / "settings.json",
        secret_manager=stub,
        key_pair_manager=kpm,
    )
    app.dependency_overrides[get_settings_service] = lambda: service
    app.dependency_overrides[get_key_pair_manager] = lambda: kpm

    enc_key = _encrypt_with_manager(kpm, "my-api-key")
    enc_secret = _encrypt_with_manager(kpm, "my-api-secret")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.put(
            "/api/v1/settings",
            json={"exchange": {"api_key": enc_key, "api_secret": enc_secret}},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["exchange"]["api_key_configured"] is True
    assert body["data"]["exchange"]["api_secret_configured"] is True
    assert stub._store["pnlclaw.exchange:api_key"] == "my-api-key"
    assert stub._store["pnlclaw.exchange:api_secret"] == "my-api-secret"


@pytest.mark.asyncio
async def test_plaintext_still_accepted_without_encryption(tmp_path):
    """Backward compat: plaintext secrets (no enc: prefix) still work."""
    app = create_app()
    stub = StubSecretManager()
    service = SettingsService(
        config_path=tmp_path / "settings.json",
        secret_manager=stub,
        key_pair_manager=None,
    )
    app.dependency_overrides[get_settings_service] = lambda: service

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.put(
            "/api/v1/settings",
            json={"llm": {"api_key": "sk-plain-key"}},
        )

    assert resp.status_code == 200
    assert stub._store["pnlclaw.llm:api_key"] == "sk-plain-key"
