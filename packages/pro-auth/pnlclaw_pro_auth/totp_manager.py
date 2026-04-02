"""TOTP two-factor authentication manager.

Uses :pypi:`pyotp` for secret generation and verification, and
:pypi:`qrcode` for QR code image creation.
"""

from __future__ import annotations

import base64
import io
import logging

import pyotp
import qrcode  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


class TOTPManager:
    """Generate and verify time-based one-time passwords."""

    @staticmethod
    def generate_secret() -> str:
        """Generate a new random TOTP secret (base32-encoded)."""
        return pyotp.random_base32()

    @staticmethod
    def get_provisioning_uri(
        secret: str,
        email: str,
        issuer: str = "PnLClaw Pro",
    ) -> str:
        """Build an ``otpauth://`` provisioning URI.

        This URI can be embedded in a QR code for authenticator app setup.
        """
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=email, issuer_name=issuer)

    @staticmethod
    def generate_qr_code_base64(uri: str) -> str:
        """Generate a QR code PNG from *uri* and return it as a base64 string.

        The caller can embed the result directly in an ``<img>`` tag via
        ``data:image/png;base64,{result}``.
        """
        img = qrcode.make(uri)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return base64.b64encode(buffer.read()).decode("ascii")

    @staticmethod
    def verify(secret: str, code: str) -> bool:
        """Verify a TOTP code against the secret.

        Allows a one-period clock skew in each direction to handle minor
        time drift between server and authenticator device.
        """
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)
