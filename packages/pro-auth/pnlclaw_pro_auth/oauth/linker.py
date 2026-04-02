"""Account linking — connect/disconnect OAuth providers to user accounts.

Works against repository protocols so that storage details stay in
``pnlclaw_pro_storage``.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol
from uuid import UUID

from pnlclaw_pro_auth.errors import AuthenticationError, OAuthError
from pnlclaw_pro_auth.models import OAuthUserInfo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Repository protocols
# ---------------------------------------------------------------------------


class OAuthAccountRepository(Protocol):
    """Minimal persistence interface for OAuth account records."""

    async def get_by_provider_uid(
        self, provider: str, provider_user_id: str
    ) -> dict[str, Any] | None:
        """Look up an OAuth account by provider + provider user ID."""
        ...

    async def create(
        self,
        user_id: UUID,
        provider: str,
        provider_user_id: str,
        provider_email: str | None,
        provider_name: str | None,
        provider_avatar: str | None,
    ) -> dict[str, Any]:
        """Create a new OAuth account link and return it as a dict."""
        ...

    async def delete(self, user_id: UUID, provider: str) -> None:
        """Remove an OAuth account link."""
        ...

    async def count_for_user(self, user_id: UUID) -> int:
        """Return the number of OAuth accounts linked to a user."""
        ...


class UserRepository(Protocol):
    """Minimal persistence interface for user records."""

    async def get_by_id(self, user_id: UUID) -> dict[str, Any] | None:
        """Return user dict by ID, or None."""
        ...


# ---------------------------------------------------------------------------
# AccountLinker
# ---------------------------------------------------------------------------


class AccountLinker:
    """Link and unlink OAuth provider accounts to PnLClaw users.

    Args:
        oauth_repo: Persistence layer for OAuth account records.
        user_repo: Persistence layer for user records.
    """

    def __init__(
        self,
        oauth_repo: OAuthAccountRepository,
        user_repo: UserRepository,
    ) -> None:
        self._oauth = oauth_repo
        self._users = user_repo

    async def link_account(
        self,
        user_id: UUID,
        oauth_info: OAuthUserInfo,
    ) -> dict[str, Any]:
        """Link an OAuth provider account to an existing user.

        Raises:
            OAuthError: If the provider account is already linked to a
                different user.
            AuthenticationError: If the target user does not exist.

        Returns:
            The newly created OAuth account record as a dict.
        """
        # Ensure user exists
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise AuthenticationError("User not found")

        # Check if provider_user_id is already linked to another user
        existing = await self._oauth.get_by_provider_uid(
            oauth_info.provider, oauth_info.provider_user_id
        )
        if existing is not None:
            existing_user_id = existing.get("user_id")
            if str(existing_user_id) != str(user_id):
                raise OAuthError(
                    f"This {oauth_info.provider} account is already linked to another user"
                )
            # Already linked to the same user — return existing
            return existing

        record = await self._oauth.create(
            user_id=user_id,
            provider=oauth_info.provider,
            provider_user_id=oauth_info.provider_user_id,
            provider_email=oauth_info.email,
            provider_name=oauth_info.name,
            provider_avatar=oauth_info.avatar_url,
        )
        logger.info(
            "Linked %s account (%s) to user %s",
            oauth_info.provider,
            oauth_info.provider_user_id,
            user_id,
        )
        return record

    async def unlink_account(self, user_id: UUID, provider: str) -> None:
        """Unlink an OAuth provider from a user.

        Raises:
            OAuthError: If removing this provider would leave the user
                with zero linked OAuth accounts (they would be locked
                out).
        """
        count = await self._oauth.count_for_user(user_id)
        if count <= 1:
            raise OAuthError(
                "Cannot unlink the last OAuth provider — the user would have "
                "no remaining login method"
            )

        await self._oauth.delete(user_id, provider)
        logger.info("Unlinked %s from user %s", provider, user_id)
