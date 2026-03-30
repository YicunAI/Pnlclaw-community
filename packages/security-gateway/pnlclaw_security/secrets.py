"""Secret management — env + file + OS keychain sources.

Distilled from OpenClaw src/secrets/.
Implements HC-07: Secrets never enter prompts, logs, or frontend storage.
"""

from __future__ import annotations

import os
import stat
import sys
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Secret source enum
# ---------------------------------------------------------------------------


class SecretSource(str, Enum):
    """Where a secret is resolved from."""

    ENV = "env"
    FILE = "file"
    KEYRING = "keyring"


# ---------------------------------------------------------------------------
# Secret reference model
# ---------------------------------------------------------------------------


class SecretRef(BaseModel):
    """A pointer to a secret value in a specific source.

    Examples::

        SecretRef(source="env", id="OPENAI_API_KEY")
        SecretRef(source="file", provider="exchange", id="binance_key")
        SecretRef(source="keyring", provider="pnlclaw", id="openai_api_key")
    """

    source: SecretSource
    provider: str = Field(default="", description="Service name / path prefix")
    id: str = Field(description="Key name within the source")


# ---------------------------------------------------------------------------
# Resolved secret — intentionally NOT a Pydantic model
# ---------------------------------------------------------------------------


class SecretResolutionError(Exception):
    """Raised when a secret cannot be resolved."""


class ResolvedSecret:
    """A resolved secret value with safety guards.

    The plaintext value is **never** exposed through ``__repr__`` or ``__str__``.
    Use the :meth:`use` method to access it explicitly.
    """

    __slots__ = ("_value", "source", "ref")

    def __init__(self, value: str, source: SecretSource, ref: SecretRef) -> None:
        self._value = value
        self.source = source
        self.ref = ref

    def use(self) -> str:
        """Return the plaintext secret value.

        This is the **only** way to access the secret. The method name
        is deliberately explicit to prevent accidental logging.
        """
        return self._value

    def __repr__(self) -> str:
        return f"ResolvedSecret(ref={self.ref!r}, redacted)"

    def __str__(self) -> str:
        return "***"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ResolvedSecret):
            return self._value == other._value and self.ref == other.ref
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self._value, self.ref.source, self.ref.provider, self.ref.id))


# ---------------------------------------------------------------------------
# Secret Manager
# ---------------------------------------------------------------------------

# Maximum file size for secret files (1 MB)
_MAX_FILE_BYTES = 1_048_576


class SecretManager:
    """Resolve and persist secrets from environment variables, files, or OS keychain.

    Args:
        base_dir: Root directory for file-based secrets.
            Defaults to ``~/.pnlclaw/secrets/``.
        keyring_required_for_store: If ``True`` (default), ``store``/``delete``
            operations require keyring backend and do not fallback to plaintext file.
    """

    def __init__(
        self,
        base_dir: Path | None = None,
        *,
        keyring_required_for_store: bool = True,
    ) -> None:
        self._base_dir = base_dir or Path.home() / ".pnlclaw" / "secrets"
        self._cache: dict[str, ResolvedSecret] = {}
        self._keyring_required_for_store = keyring_required_for_store

    async def resolve(self, ref: SecretRef) -> ResolvedSecret:
        """Resolve a secret reference.

        Results are cached by reference identity. Raises
        :class:`SecretResolutionError` if the secret cannot be found.
        """
        cache_key = f"{ref.source}:{ref.provider}:{ref.id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        if ref.source == SecretSource.ENV:
            value = self._resolve_env(ref)
        elif ref.source == SecretSource.FILE:
            value = self._resolve_file(ref)
        elif ref.source == SecretSource.KEYRING:
            value = await self._resolve_keyring(ref)
        else:
            raise SecretResolutionError(f"Unknown secret source: {ref.source}")

        resolved = ResolvedSecret(value=value, source=ref.source, ref=ref)
        self._cache[cache_key] = resolved
        return resolved

    def clear_cache(self) -> None:
        """Clear the resolved secret cache."""
        self._cache.clear()

    def keyring_available(self) -> bool:
        """Return whether keyring backend is available in this runtime."""
        try:
            import keyring  # type: ignore[import-untyped]

            return keyring is not None
        except ImportError:
            return False

    async def exists(self, ref: SecretRef) -> bool:
        """Return True if the secret exists in the referenced source."""
        try:
            await self.resolve(ref)
            return True
        except SecretResolutionError:
            return False

    async def store(self, ref: SecretRef, value: str) -> None:
        """Persist a secret value for the given reference."""
        if ref.source == SecretSource.KEYRING:
            await self._store_keyring(ref, value)
            self._cache.pop(f"{ref.source}:{ref.provider}:{ref.id}", None)
            return

        if self._keyring_required_for_store:
            raise SecretResolutionError(
                "Secret persistence requires keyring backend; refusing insecure storage."
            )

        if ref.source == SecretSource.FILE:
            self._store_file(ref, value)
            self._cache.pop(f"{ref.source}:{ref.provider}:{ref.id}", None)
            return

        raise SecretResolutionError(
            f"Store operation is not supported for source: {ref.source}"
        )

    async def delete(self, ref: SecretRef) -> None:
        """Delete a persisted secret for the given reference."""
        if ref.source == SecretSource.KEYRING:
            await self._delete_keyring(ref)
            self._cache.pop(f"{ref.source}:{ref.provider}:{ref.id}", None)
            return

        if self._keyring_required_for_store:
            raise SecretResolutionError(
                "Secret deletion requires keyring backend; refusing insecure storage."
            )

        if ref.source == SecretSource.FILE:
            self._delete_file(ref)
            self._cache.pop(f"{ref.source}:{ref.provider}:{ref.id}", None)
            return

        raise SecretResolutionError(
            f"Delete operation is not supported for source: {ref.source}"
        )

    # -- source resolvers ----------------------------------------------------

    def _resolve_env(self, ref: SecretRef) -> str:
        """Resolve from environment variable."""
        value = os.environ.get(ref.id)
        if value is None:
            raise SecretResolutionError(f"Environment variable not found: {ref.id}")
        return value

    def _resolve_file(self, ref: SecretRef) -> str:
        """Resolve from a file.

        The file path is ``base_dir / provider / id``.
        Rejects files that are world-readable (POSIX) or too large.
        """
        if ref.provider:
            file_path = self._base_dir / ref.provider / ref.id
        else:
            file_path = self._base_dir / ref.id

        if not file_path.exists():
            raise SecretResolutionError(f"Secret file not found: {file_path}")

        # Security: check file permissions on POSIX systems
        if sys.platform != "win32":
            file_stat = file_path.stat()
            mode = file_stat.st_mode
            if mode & (stat.S_IRGRP | stat.S_IROTH):
                raise SecretResolutionError(
                    f"Secret file {file_path} is readable by group/others. "
                    f"Fix with: chmod 600 {file_path}"
                )

        # Size check
        file_size = file_path.stat().st_size
        if file_size > _MAX_FILE_BYTES:
            raise SecretResolutionError(f"Secret file {file_path} exceeds {_MAX_FILE_BYTES} bytes")

        return file_path.read_text(encoding="utf-8").strip()

    async def _resolve_keyring(self, ref: SecretRef) -> str:
        """Resolve from OS keychain via the ``keyring`` library.

        The ``keyring`` library is an optional dependency. If not installed,
        raises :class:`SecretResolutionError` with a helpful message.
        """
        keyring = self._import_keyring()

        service = ref.provider or "pnlclaw"
        value = keyring.get_password(service, ref.id)
        if value is None:
            raise SecretResolutionError(
                f"No keyring entry found for service={service!r}, key={ref.id!r}"
            )
        return value

    async def _store_keyring(self, ref: SecretRef, value: str) -> None:
        keyring = self._import_keyring()
        service = ref.provider or "pnlclaw"
        keyring.set_password(service, ref.id, value)

    async def _delete_keyring(self, ref: SecretRef) -> None:
        keyring = self._import_keyring()
        service = ref.provider or "pnlclaw"
        try:
            keyring.delete_password(service, ref.id)
        except Exception:
            # Missing key or backend-specific errors are treated as already removed.
            return

    def _store_file(self, ref: SecretRef, value: str) -> None:
        file_path = self._file_path(ref)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(value.strip(), encoding="utf-8")
        if sys.platform != "win32":
            file_path.chmod(0o600)

    def _delete_file(self, ref: SecretRef) -> None:
        file_path = self._file_path(ref)
        try:
            file_path.unlink()
        except FileNotFoundError:
            return

    def _file_path(self, ref: SecretRef) -> Path:
        if ref.provider:
            return self._base_dir / ref.provider / ref.id
        return self._base_dir / ref.id

    def _import_keyring(self) -> Any:
        try:
            import keyring  # type: ignore[import-untyped]
        except ImportError:
            raise SecretResolutionError(
                "keyring library not installed. Install with: pip install pnlclaw-security[keyring]"
            ) from None
        return keyring
