"""User tag repository — tag CRUD and user-tag assignment management."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select

from pnlclaw_pro_storage.models import UserTag, UserTagAssignment
from pnlclaw_pro_storage.postgres import AsyncPostgresManager


class UserTagRepository:
    """Async repository for the ``user_tags`` and ``user_tag_assignments`` tables."""

    def __init__(self, db: AsyncPostgresManager) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Tag CRUD
    # ------------------------------------------------------------------

    async def create_tag(
        self,
        name: str,
        color: str | None = None,
        description: str | None = None,
        created_by: uuid.UUID | None = None,
    ) -> UserTag:
        """Create a new tag and return the persisted row."""
        tag = UserTag(name=name, color=color, description=description, created_by=created_by)
        async with self._db.session() as session:
            session.add(tag)
            await session.flush()
            await session.refresh(tag)
            return tag

    async def list_tags(self) -> list[UserTag]:
        """Return all tags with their usage counts.

        Each returned ``UserTag`` has an additional transient attribute
        ``usage_count`` set by this method. (The attribute is set on the
        Python object but is not persisted.)
        """
        async with self._db.session() as session:
            count_subq = (
                select(
                    UserTagAssignment.tag_id,
                    func.count().label("usage_count"),
                )
                .group_by(UserTagAssignment.tag_id)
                .subquery()
            )

            stmt = (
                select(UserTag, func.coalesce(count_subq.c.usage_count, 0).label("usage_count"))
                .outerjoin(count_subq, UserTag.id == count_subq.c.tag_id)
                .order_by(UserTag.name)
            )
            result = await session.execute(stmt)
            tags: list[UserTag] = []
            for row in result.all():
                tag = row[0]
                tag.usage_count = row[1]  # type: ignore[attr-defined]
                tags.append(tag)
            return tags

    async def update_tag(
        self,
        tag_id: uuid.UUID,
        name: str | None = None,
        color: str | None = None,
        description: str | None = None,
    ) -> UserTag:
        """Update a tag's name, color, and/or description.

        Raises ``ValueError`` if the tag does not exist.
        """
        async with self._db.session() as session:
            tag = await session.get(UserTag, tag_id)
            if tag is None:
                raise ValueError(f"Tag {tag_id} not found")
            if name is not None:
                tag.name = name
            if color is not None:
                tag.color = color
            if description is not None:
                tag.description = description
            await session.flush()
            await session.refresh(tag)
            return tag

    async def delete_tag(self, tag_id: uuid.UUID) -> None:
        """Delete a tag and all its assignments (cascade)."""
        async with self._db.session() as session:
            stmt = delete(UserTag).where(UserTag.id == tag_id)
            await session.execute(stmt)

    # ------------------------------------------------------------------
    # Tag assignments
    # ------------------------------------------------------------------

    async def assign_tag(
        self,
        user_id: uuid.UUID,
        tag_id: uuid.UUID,
        assigned_by: uuid.UUID | None = None,
    ) -> None:
        """Assign a tag to a user. No-op if already assigned."""
        async with self._db.session() as session:
            exists_stmt = select(UserTagAssignment).where(
                UserTagAssignment.user_id == user_id,
                UserTagAssignment.tag_id == tag_id,
            )
            existing = (await session.execute(exists_stmt)).scalar_one_or_none()
            if existing is not None:
                return
            assignment = UserTagAssignment(
                user_id=user_id,
                tag_id=tag_id,
                assigned_by=assigned_by,
            )
            session.add(assignment)

    async def remove_tag(self, user_id: uuid.UUID, tag_id: uuid.UUID) -> None:
        """Remove a tag assignment from a user."""
        async with self._db.session() as session:
            stmt = delete(UserTagAssignment).where(
                UserTagAssignment.user_id == user_id,
                UserTagAssignment.tag_id == tag_id,
            )
            await session.execute(stmt)

    async def get_user_tags(self, user_id: uuid.UUID) -> list[UserTag]:
        """Return all tags assigned to a user."""
        async with self._db.session() as session:
            stmt = (
                select(UserTag)
                .join(UserTagAssignment, UserTag.id == UserTagAssignment.tag_id)
                .where(UserTagAssignment.user_id == user_id)
                .order_by(UserTag.name)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
