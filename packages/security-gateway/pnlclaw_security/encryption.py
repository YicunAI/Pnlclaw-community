"""Application-layer Fernet encryption for secrets at rest.

Provides symmetric encrypt/decrypt using Fernet (AES-128-CBC + HMAC-SHA256).
Used to protect secrets stored in keyring, SQLite, and PostgreSQL on headless
servers where the OS keychain may be a plaintext file backend.

The encryption key is loaded from the ``PNLCLAW_ENCRYPTION_KEY`` environment
variable or derived from a passphrase.  When unavailable, operations degrade
gracefully with a logged warning rather than crashing.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from functools import lru_cache

logger = logging.getLogger(__name__)

_FERNET_PREFIX = "fernet:"
_ENCRYPTION_KEY_ENV = "PNLCLAW_ENCRYPTION_KEY"


def _load_fernet_key() -> bytes | None:
    """Load or derive a 32-byte Fernet key from environment."""
    raw = os.environ.get(_ENCRYPTION_KEY_ENV)
    if not raw:
        return None

    raw = raw.strip()
    try:
        decoded = base64.urlsafe_b64decode(raw)
        if len(decoded) == 32:
            return raw.encode() if isinstance(raw, str) else raw
    except Exception:
        pass

    derived = hashlib.pbkdf2_hmac("sha256", raw.encode(), b"pnlclaw-salt-v1", 100_000)
    return base64.urlsafe_b64encode(derived)


@lru_cache(maxsize=1)
def _get_fernet():
    """Return a cached Fernet instance or None if key is unavailable."""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        logger.warning("cryptography library not installed; field encryption disabled")
        return None

    key = _load_fernet_key()
    if key is None:
        logger.warning(
            "PNLCLAW_ENCRYPTION_KEY not set; field encryption disabled — "
            "secrets will be stored without application-layer encryption"
        )
        return None

    try:
        return Fernet(key)
    except Exception:
        logger.error("Invalid PNLCLAW_ENCRYPTION_KEY — cannot initialize Fernet")
        return None


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string, returning a ``fernet:``-prefixed ciphertext.

    If encryption is unavailable, returns the plaintext unchanged.
    """
    if not plaintext:
        return plaintext

    f = _get_fernet()
    if f is None:
        return plaintext

    token = f.encrypt(plaintext.encode("utf-8"))
    return _FERNET_PREFIX + token.decode("ascii")


def decrypt_value(stored: str) -> str:
    """Decrypt a stored value.  If it lacks the ``fernet:`` prefix, returns as-is.

    Raises ``ValueError`` when the prefix is present but decryption fails
    (wrong key, corrupted data).
    """
    if not stored or not stored.startswith(_FERNET_PREFIX):
        return stored

    f = _get_fernet()
    if f is None:
        raise ValueError(
            "Cannot decrypt fernet-encrypted value: PNLCLAW_ENCRYPTION_KEY not configured"
        )

    token = stored[len(_FERNET_PREFIX) :].encode("ascii")
    try:
        return f.decrypt(token).decode("utf-8")
    except Exception as exc:
        raise ValueError("Fernet decryption failed — wrong key or corrupted data") from exc


def is_encryption_available() -> bool:
    """Return whether Fernet encryption is configured and operational."""
    return _get_fernet() is not None


def encryption_status() -> dict[str, object]:
    """Return a diagnostic dict describing the encryption subsystem."""
    key_set = bool(os.environ.get(_ENCRYPTION_KEY_ENV, "").strip())
    try:
        from cryptography.fernet import Fernet  # noqa: F401

        lib_ok = True
    except ImportError:
        lib_ok = False

    available = is_encryption_available()
    return {
        "encryption_key_configured": key_set,
        "cryptography_library_installed": lib_ok,
        "field_encryption_active": available,
    }
