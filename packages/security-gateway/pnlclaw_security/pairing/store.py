"""Pairing state store — 8-character codes with TTL.

Distilled from OpenClaw src/pairing/pairing-store.ts.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Excludes 0/O/1/I/L to prevent human-readability confusion
UNAMBIGUOUS_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8
DEFAULT_TTL_SECONDS = 3600  # 1 hour
MAX_PENDING = 3
_MAX_GENERATION_ATTEMPTS = 500


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class PairingRequest(BaseModel):
    """A pending device pairing request."""

    code: str = Field(description="8-character pairing code")
    created_at: float = Field(default_factory=time.time)
    expires_at: float = Field(description="Unix timestamp when code expires")
    device_info: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class PairingStore:
    """File-backed store for pending pairing requests.

    Args:
        store_dir: Directory for persistence.
            Defaults to ``~/.pnlclaw/pairing/``.
        ttl_seconds: Time-to-live for pairing codes.
    """

    def __init__(
        self,
        store_dir: Path | None = None,
        *,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._store_dir = store_dir or Path.home() / ".pnlclaw" / "pairing"
        self._ttl = ttl_seconds
        self._store_dir.mkdir(parents=True, exist_ok=True)

    @property
    def _store_file(self) -> Path:
        return self._store_dir / "pending.json"

    def generate_code(self) -> str:
        """Generate a cryptographically random 8-character pairing code.

        Uses the unambiguous alphabet (no 0/O/1/I/L) and ``secrets.choice``
        for cryptographic randomness.
        """
        return "".join(secrets.choice(UNAMBIGUOUS_ALPHABET) for _ in range(CODE_LENGTH))

    def create_request(self, device_info: dict[str, str] | None = None) -> PairingRequest:
        """Create a new pairing request.

        Enforces :data:`MAX_PENDING` limit by removing the oldest request
        if necessary. Expired requests are purged first.

        Raises:
            RuntimeError: If a unique code cannot be generated after
                many attempts (extremely unlikely).
        """
        pending = self._load()
        self._purge_expired(pending)

        # Enforce MAX_PENDING: remove oldest if at limit
        while len(pending) >= MAX_PENDING:
            pending.pop(0)

        # Generate unique code
        existing_codes = {r.code for r in pending}
        for _ in range(_MAX_GENERATION_ATTEMPTS):
            code = self.generate_code()
            if code not in existing_codes:
                break
        else:
            raise RuntimeError("Failed to generate unique pairing code")

        now = time.time()
        request = PairingRequest(
            code=code,
            created_at=now,
            expires_at=now + self._ttl,
            device_info=device_info or {},
        )
        pending.append(request)
        self._save(pending)
        return request

    def get_pending(self) -> list[PairingRequest]:
        """Return all non-expired pending requests."""
        pending = self._load()
        self._purge_expired(pending)
        self._save(pending)
        return list(pending)

    def remove_request(self, code: str) -> bool:
        """Remove a pending request by code.

        Returns ``True`` if the request was found and removed.
        """
        pending = self._load()
        original_len = len(pending)
        pending = [r for r in pending if r.code != code.strip().upper()]
        if len(pending) < original_len:
            self._save(pending)
            return True
        return False

    # -- internal ------------------------------------------------------------

    def _purge_expired(self, pending: list[PairingRequest]) -> None:
        """Remove expired entries in-place."""
        now = time.time()
        pending[:] = [r for r in pending if r.expires_at > now]

    def _load(self) -> list[PairingRequest]:
        """Load pending requests from disk."""
        if not self._store_file.exists():
            return []
        try:
            data = json.loads(self._store_file.read_text(encoding="utf-8"))
            return [PairingRequest.model_validate(item) for item in data]
        except (json.JSONDecodeError, Exception):
            return []

    def _save(self, requests: list[PairingRequest]) -> None:
        """Atomically save pending requests to disk."""
        data = [r.model_dump() for r in requests]
        content = json.dumps(data, indent=2)

        # Atomic write: write to temp file then rename
        tmp_file = self._store_file.with_suffix(".tmp")
        fd = os.open(str(tmp_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, content.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        tmp_file.replace(self._store_file)
