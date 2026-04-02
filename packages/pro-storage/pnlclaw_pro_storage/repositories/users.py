"""User repository — CRUD and status management for User rows."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import selectinload

from pnlclaw_pro_storage.models import User, UserTag, UserTagAssignment
from pnlclaw_pro_storage.postgres import AsyncPostgresManager

_ALLOWED_SORT_COLUMNS = {
    "created_at", "display_name", "email", "status", "role",
    "last_login_at", "login_count",
}


def _escape_like(s: str) -> str:
    """Escape LIKE metacharacters so they match literally."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class UserRepository:
    """Async repository for the ``users`` table."""

    def __init__(self, db: AsyncPostgresManager) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create(
        self,
        display_name: str,
        email: str | None = None,
        avatar_url: str | None = None,
        bio: str | None = None,
        locale: str | None = None,
        timezone_: str | None = None,
        role: str = "user",
    ) -> User:
        """Insert a new user and return the persisted instance."""
        user = User(
            display_name=display_name,
            email=email,
            avatar_url=avatar_url,
            bio=bio,
            locale=locale,
            timezone=timezone_,
            role=role,
        )
        async with self._db.session() as session:
            session.add(user)
            await session.flush()
            await session.refresh(user)
            return user

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """Return a user by primary key, or ``None``."""
        from pnlclaw_pro_storage.models import OAuthAccount

        async with self._db.session() as session:
            stmt = (
                select(User)
                .where(User.id == user_id)
                .options(
                    selectinload(User.oauth_accounts),
                    selectinload(User.tag_assignments).selectinload(UserTagAssignment.tag),
                )
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Return the first non-deleted user matching *email*."""
        async with self._db.session() as session:
            stmt = (
                select(User)
                .where(User.email == email, User.deleted_at.is_(None))
                .options(
                    selectinload(User.oauth_accounts),
                    selectinload(User.tag_assignments).selectinload(UserTagAssignment.tag),
                )
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_users(
        self,
        *,
        search: str | None = None,
        status: str | None = None,
        role: str | None = None,
        provider: str | None = None,
        tag: str | None = None,
        country: str | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[User], int]:
        """Return a page of users with a total count.

        Parameters
        ----------
        search:
            Case-insensitive partial match on display_name or email.
        status:
            Exact match on ``User.status``.
        role:
            Exact match on ``User.role``.
        provider:
            Filter to users that have an OAuth account with this provider.
        tag:
            Filter to users that have the given tag name assigned.
        country:
            Exact match on ``User.last_country``.
        sort_by:
            Column name to order by (default ``created_at``).
        sort_order:
            ``"asc"`` or ``"desc"`` (default ``"desc"``).
        offset / limit:
            Pagination.
        """
        from pnlclaw_pro_storage.models import OAuthAccount

        async with self._db.session() as session:
            base = (
                select(User)
                .where(User.deleted_at.is_(None))
                .options(
                    selectinload(User.oauth_accounts),
                    selectinload(User.tag_assignments).selectinload(UserTagAssignment.tag),
                )
            )

            if search:
                pattern = f"%{_escape_like(search)}%"
                base = base.where(
                    or_(
                        User.display_name.ilike(pattern),
                        User.email.ilike(pattern),
                    )
                )

            if status:
                base = base.where(User.status == status)

            if role:
                base = base.where(User.role == role)

            if country:
                base = base.where(User.last_country == country)

            if provider:
                base = base.where(
                    User.id.in_(
                        select(OAuthAccount.user_id).where(
                            OAuthAccount.provider == provider
                        )
                    )
                )

            if tag:
                base = base.where(
                    User.id.in_(
                        select(UserTagAssignment.user_id)
                        .join(UserTag, UserTagAssignment.tag_id == UserTag.id)
                        .where(UserTag.name == tag)
                    )
                )

            # Total count (before pagination)
            count_stmt = select(func.count()).select_from(base.subquery())
            total: int = (await session.execute(count_stmt)).scalar_one()

            # Ordering
            if sort_by not in _ALLOWED_SORT_COLUMNS:
                sort_by = "created_at"
            sort_col = getattr(User, sort_by, User.created_at)
            order_expr = sort_col.asc() if sort_order == "asc" else sort_col.desc()
            base = base.order_by(order_expr).offset(offset).limit(limit)

            result = await session.execute(base)
            users = list(result.scalars().all())
            return users, total

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update(self, user_id: uuid.UUID, **fields: Any) -> User:
        """Update arbitrary columns on a user and return the refreshed row.

        Raises ``ValueError`` if the user does not exist.
        """
        async with self._db.session() as session:
            user = await session.get(User, user_id)
            if user is None:
                raise ValueError(f"User {user_id} not found")
            for key, value in fields.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            await session.flush()
            await session.refresh(user)
            return user

    # ------------------------------------------------------------------
    # Status transitions
    # ------------------------------------------------------------------

    async def ban(self, user_id: uuid.UUID, reason: str) -> User:
        """Set a user's status to ``banned`` with a reason."""
        return await self.update(user_id, status="banned", ban_reason=reason)

    async def suspend(self, user_id: uuid.UUID) -> User:
        """Set a user's status to ``suspended``."""
        return await self.update(user_id, status="suspended")

    async def activate(self, user_id: uuid.UUID) -> User:
        """Set a user's status to ``active`` and clear any ban reason."""
        return await self.update(user_id, status="active", ban_reason=None)

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    async def soft_delete(self, user_id: uuid.UUID) -> None:
        """Mark a user as deleted without removing the row."""
        now = datetime.now(timezone.utc)
        async with self._db.session() as session:
            stmt = (
                update(User)
                .where(User.id == user_id)
                .values(deleted_at=now, status="deleted")
            )
            await session.execute(stmt)

    async def hard_delete_expired(self, days: int = 30) -> int:
        """Permanently delete rows soft-deleted more than *days* ago.

        Returns the number of rows removed.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        async with self._db.session() as session:
            stmt = (
                delete(User)
                .where(User.deleted_at.isnot(None), User.deleted_at < cutoff)
            )
            result = await session.execute(stmt)
            return result.rowcount  # type: ignore[return-value]
