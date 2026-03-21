"""Pairing token management — cryptographically secure tokens.

Distilled from OpenClaw src/infra/pairing-token.ts.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import time
from pathlib import Path

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TOKEN_TTL_SECONDS = 86_400  # 24 hours
_TOKEN_BYTES = 32  # 256-bit tokens


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class PairingToken(BaseModel):
    """A device pairing token with scopes and expiration."""

    token: str = Field(description="URL-safe random token")
    device_id: str = Field(description="Paired device identifier")
    created_at: float = Field(default_factory=time.time)
    expires_at: float = Field(description="Unix timestamp when token expires")
    scopes: list[str] = Field(default_factory=lambda: ["read"])


# ---------------------------------------------------------------------------
# Token store
# ---------------------------------------------------------------------------


class TokenStore:
    """File-backed store for pairing tokens.

    All token comparisons use ``hmac.compare_digest`` for constant-time
    comparison to prevent timing attacks.

    Args:
        store_dir: Directory for persistence.
            Defaults to ``~/.pnlclaw/pairing/``.
    """

    def __init__(self, store_dir: Path | None = None) -> None:
        self._store_dir = store_dir or Path.home() / ".pnlclaw" / "pairing"
        self._store_dir.mkdir(parents=True, exist_ok=True)

    @property
    def _store_file(self) -> Path:
        return self._store_dir / "tokens.json"

    def issue_token(
        self,
        device_id: str,
        *,
        scopes: list[str] | None = None,
        ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS,
    ) -> PairingToken:
        """Issue a new pairing token for a device.

        Args:
            device_id: Identifier for the paired device.
            scopes: Permission scopes. Defaults to ``["read"]``.
            ttl_seconds: Token lifetime in seconds.

        Returns:
            The newly issued :class:`PairingToken`.
        """
        now = time.time()
        token = PairingToken(
            token=secrets.token_urlsafe(_TOKEN_BYTES),
            device_id=device_id,
            created_at=now,
            expires_at=now + ttl_seconds,
            scopes=scopes or ["read"],
        )

        tokens = self._load()
        # Remove any existing token for this device
        tokens = [t for t in tokens if t.device_id != device_id]
        tokens.append(token)
        self._save(tokens)
        return token

    def validate_token(self, raw_token: str) -> PairingToken | None:
        """Validate a token and return its metadata if valid.

        Uses constant-time comparison via ``hmac.compare_digest``.
        Iterates all tokens regardless of match position.

        Returns:
            :class:`PairingToken` if valid and not expired, ``None`` otherwise.
        """
        tokens = self._load()
        now = time.time()
        matched: PairingToken | None = None

        for stored in tokens:
            is_match = hmac.compare_digest(
                raw_token.encode("utf-8"),
                stored.token.encode("utf-8"),
            )
            if is_match and stored.expires_at > now:
                matched = stored
            # Continue iterating (constant-time)

        return matched

    def revoke_token(self, device_id: str) -> bool:
        """Revoke the token for a specific device.

        Returns ``True`` if a token was found and revoked.
        """
        tokens = self._load()
        original_len = len(tokens)
        tokens = [t for t in tokens if t.device_id != device_id]
        if len(tokens) < original_len:
            self._save(tokens)
            return True
        return False

    def revoke_all(self) -> int:
        """Revoke all tokens. Returns the number revoked."""
        tokens = self._load()
        count = len(tokens)
        if count > 0:
            self._save([])
        return count

    # -- internal ------------------------------------------------------------

    def _load(self) -> list[PairingToken]:
        if not self._store_file.exists():
            return []
        try:
            data = json.loads(self._store_file.read_text(encoding="utf-8"))
            return [PairingToken.model_validate(item) for item in data]
        except (json.JSONDecodeError, Exception):
            return []

    def _save(self, tokens: list[PairingToken]) -> None:
        data = [t.model_dump() for t in tokens]
        content = json.dumps(data, indent=2)

        tmp_file = self._store_file.with_suffix(".tmp")
        fd = os.open(str(tmp_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, content.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        tmp_file.replace(self._store_file)
