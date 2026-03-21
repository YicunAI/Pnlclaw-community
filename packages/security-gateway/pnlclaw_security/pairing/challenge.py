"""Pairing code challenge and verification — constant-time comparison.

Distilled from OpenClaw src/pairing/pairing-challenge.ts.
"""

from __future__ import annotations

import hmac

from pydantic import BaseModel, Field

from pnlclaw_security.pairing.store import PairingRequest, PairingStore


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class ChallengeResult(BaseModel):
    """Result of a pairing code verification attempt."""

    success: bool
    device_info: dict[str, str] = Field(default_factory=dict)
    error: str | None = None


# ---------------------------------------------------------------------------
# Challenge verifier
# ---------------------------------------------------------------------------


class PairingChallenge:
    """Verify pairing codes with constant-time comparison.

    Security properties:
    - Uses ``hmac.compare_digest`` for timing-attack resistance.
    - Iterates **all** pending codes before returning (constant-time
      regardless of match position).
    - Does not reveal whether a code exists vs. is expired.

    Args:
        store: The :class:`PairingStore` holding pending requests.
    """

    def __init__(self, store: PairingStore) -> None:
        self._store = store

    def verify_code(self, submitted_code: str) -> ChallengeResult:
        """Verify a submitted pairing code.

        Args:
            submitted_code: The code entered by the user.

        Returns:
            :class:`ChallengeResult` with ``success=True`` and device info
            if the code is valid, or ``success=False`` with a generic
            error message otherwise.
        """
        normalised = submitted_code.strip().upper()
        pending = self._store.get_pending()

        matched = self._constant_time_lookup(normalised, pending)

        if matched is not None:
            # Consume the code (one-time use)
            self._store.remove_request(matched.code)
            return ChallengeResult(
                success=True,
                device_info=matched.device_info,
            )

        # Generic error: do NOT distinguish "not found" from "expired"
        return ChallengeResult(
            success=False,
            error="Invalid or expired pairing code",
        )

    @staticmethod
    def _constant_time_lookup(
        code: str,
        pending: list[PairingRequest],
    ) -> PairingRequest | None:
        """Look up a code in the pending list with constant-time iteration.

        Compares against **every** pending code regardless of whether a
        match is found early, preventing timing-based enumeration.
        """
        matched: PairingRequest | None = None

        for request in pending:
            # hmac.compare_digest provides constant-time string comparison
            if hmac.compare_digest(code.encode("utf-8"), request.code.encode("utf-8")):
                matched = request
            # Continue iterating even after match (constant-time)

        return matched
