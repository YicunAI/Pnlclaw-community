"""RSA key pair management for encrypted secret transport.

Generates an ephemeral RSA-2048 key pair at startup.  The frontend encrypts
sensitive values (API keys, secrets) with the public key before sending them
over HTTP.  The backend decrypts with the private key, then stores plaintext
in the OS keyring.

The key pair lives only in process memory and is never persisted to disk.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

logger = logging.getLogger(__name__)

# Marker prefix that the frontend wraps around ciphertext so the backend
# can distinguish encrypted values from plaintext.
ENCRYPTED_PREFIX = "enc:"


class KeyPairManager:
    """Ephemeral RSA-2048 key pair for frontend-to-backend secret transport."""

    def __init__(self) -> None:
        self._private_key: RSAPrivateKey = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )
        self._public_key: RSAPublicKey = self._private_key.public_key()
        logger.info("Generated ephemeral RSA-2048 key pair for secret transport")

    def public_key_jwk(self) -> dict[str, Any]:
        """Export the public key as a JWK dict (for Web Crypto API import)."""
        pub_numbers = self._public_key.public_numbers()

        def _int_to_b64url(value: int, length: int) -> str:
            raw = value.to_bytes(length, byteorder="big")
            return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

        n_bytes = (self._public_key.key_size + 7) // 8
        return {
            "kty": "RSA",
            "alg": "RSA-OAEP-256",
            "use": "enc",
            "n": _int_to_b64url(pub_numbers.n, n_bytes),
            "e": _int_to_b64url(pub_numbers.e, 3),
        }

    def decrypt(self, ciphertext_b64: str) -> str:
        """Decrypt a Base64-encoded RSA-OAEP-256 ciphertext back to plaintext.

        Args:
            ciphertext_b64: Base64 (standard or URL-safe) encoded ciphertext
                produced by the frontend using the matching public key.

        Raises:
            ValueError: If decryption fails (wrong key, corrupt data, etc.).
        """
        try:
            raw = base64.b64decode(ciphertext_b64)
        except Exception as exc:
            raise ValueError("Invalid base64 ciphertext") from exc

        try:
            plaintext = self._private_key.decrypt(
                raw,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None,
                ),
            )
        except Exception as exc:
            raise ValueError("RSA-OAEP decryption failed") from exc

        return plaintext.decode("utf-8")


def decrypt_if_encrypted(manager: KeyPairManager | None, value: str) -> str:
    """Return the plaintext of *value*, decrypting if it carries the ``enc:`` prefix.

    If *manager* is ``None`` or the value is not prefixed, returns *value* as-is.
    """
    if manager is None:
        return value
    if not value.startswith(ENCRYPTED_PREFIX):
        return value
    return manager.decrypt(value[len(ENCRYPTED_PREFIX):])
