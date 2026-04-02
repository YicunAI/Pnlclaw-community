"""OAuth account repository — link / unlink external identity providers."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, func, select, update

from pnlclaw_pro_storage.models import OAuthAccount
from pnlclaw_pro_storage.postgres import AsyncPostgresManager


class OAuthAccountRepository:
    """Async repository for the ``oauth_accounts`` table."""

    def __init__(self, db: AsyncPostgresManager) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create(
        self,
        user_id: uuid.UUID,
        provider: str,
        provider_user_id: str,
        provider_email: str | None = None,
        provider_name: str | None = None,
        provider_avatar: str | None = None,
        access_token: str | None = None,
        refresh_token: str | None = None,
        token_expires_at: datetime | None = None,
    ) -> OAuthAccount:
        """Insert a new OAuth account link and return the persisted row."""
        account = OAuthAccount(
            user_id=user_id,
            provider=provider,
            provider_user_id=provider_user_id,
            provider_email=provider_email,
            provider_name=provider_name,
            provider_avatar=provider_avatar,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=token_expires_at,
        )
        async with self._db.session() as session:
            session.add(account)
            await session.flush()
            await session.refresh(account)
            return account

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_provider(self, provider: str, provider_user_id: str) -> OAuthAccount | None:
        """Look up an OAuth account by its provider + external user id."""
        async with self._db.session() as session:
            stmt = select(OAuthAccount).where(
                OAuthAccount.provider == provider,
                OAuthAccount.provider_user_id == provider_user_id,
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: uuid.UUID) -> list[OAuthAccount]:
        """Return all OAuth accounts linked to a user."""
        async with self._db.session() as session:
            stmt = select(OAuthAccount).where(OAuthAccount.user_id == user_id)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_tokens(
        self,
        account_id: uuid.UUID,
        access_token: str,
        refresh_token: str | None,
        expires_at: datetime | None,
    ) -> None:
        """Overwrite the stored tokens for an OAuth account."""
        async with self._db.session() as session:
            stmt = (
                update(OAuthAccount)
                .where(OAuthAccount.id == account_id)
                .values(
                    access_token=access_token,
                    refresh_token=refresh_token,
                    token_expires_at=expires_at,
                )
            )
            await session.execute(stmt)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete(self, account_id: uuid.UUID) -> None:
        """Remove an OAuth account link."""
        async with self._db.session() as session:
            stmt = delete(OAuthAccount).where(OAuthAccount.id == account_id)
            await session.execute(stmt)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def count_for_user(self, user_id: uuid.UUID) -> int:
        """Return the number of OAuth accounts linked to a user."""
        async with self._db.session() as session:
            stmt = select(func.count()).select_from(OAuthAccount).where(OAuthAccount.user_id == user_id)
            result = await session.execute(stmt)
            return result.scalar_one()
