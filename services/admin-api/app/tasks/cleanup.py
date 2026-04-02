"""Background cleanup tasks for session, user, and invitation maintenance."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class CleanupTasks:
    """Collection of async cleanup methods for periodic maintenance."""

    def __init__(
        self,
        session_repo: Any,
        user_repo: Any,
        pg_manager: Any | None = None,
    ) -> None:
        self._session_repo = session_repo
        self._user_repo = user_repo
        self._pg = pg_manager

    async def cleanup_expired_sessions(self) -> int:
        """Delete expired sessions and refresh tokens.

        Returns the number of sessions cleaned up.
        """
        try:
            count = await self._session_repo.cleanup_expired()
            if count > 0:
                logger.info("Cleaned up %d expired sessions", count)
            return count
        except Exception:
            logger.warning("Failed to clean up expired sessions", exc_info=True)
            return 0

    async def cleanup_soft_deleted_users(self, days: int = 30) -> int:
        """Hard delete users that were soft-deleted more than N days ago.

        Args:
            days: Number of days after soft delete before hard deletion.

        Returns the number of users permanently removed.
        """
        try:
            count = await self._user_repo.hard_delete_expired(days=days)
            if count > 0:
                logger.info(
                    "Permanently deleted %d users soft-deleted more than %d days ago",
                    count,
                    days,
                )
            return count
        except Exception:
            logger.warning("Failed to clean up soft-deleted users", exc_info=True)
            return 0

    async def cleanup_expired_invitations(self) -> int:
        """Delete expired invitations.

        Returns the number of invitations removed.
        """
        try:
            if self._pg is None:
                # Try to get pg_manager from dependencies
                from app.core.dependencies import get_postgres_manager

                self._pg = get_postgres_manager()

            if self._pg is None:
                return 0

            result = await self._pg.execute("DELETE FROM invitations WHERE expires_at < NOW()")
            # Parse count from result string like "DELETE 5"
            count = 0
            if result and isinstance(result, str):
                parts = result.split()
                if len(parts) >= 2:
                    try:
                        count = int(parts[1])
                    except (ValueError, IndexError):
                        pass

            if count > 0:
                logger.info("Cleaned up %d expired invitations", count)
            return count
        except Exception:
            logger.warning("Failed to clean up expired invitations", exc_info=True)
            return 0

    async def run_all(self) -> dict[str, int]:
        """Run all cleanup tasks and return counts."""
        sessions = await self.cleanup_expired_sessions()
        users = await self.cleanup_soft_deleted_users()
        invitations = await self.cleanup_expired_invitations()
        return {
            "expired_sessions": sessions,
            "soft_deleted_users": users,
            "expired_invitations": invitations,
        }


def start_cleanup_scheduler(
    session_repo: Any,
    user_repo: Any,
    pg_manager: Any | None = None,
    interval_hours: int = 1,
) -> asyncio.Task[None]:
    """Start a background task that runs cleanup periodically.

    Args:
        session_repo: SessionRepository for session cleanup.
        user_repo: UserRepository for user cleanup.
        pg_manager: Optional AsyncPostgresManager for invitation cleanup.
        interval_hours: How often to run (default: every 1 hour).

    Returns:
        The asyncio Task, which can be cancelled on shutdown.
    """
    tasks = CleanupTasks(
        session_repo=session_repo,
        user_repo=user_repo,
        pg_manager=pg_manager,
    )

    async def _scheduler() -> None:
        logger.info(
            "Cleanup scheduler started (interval: %d hour(s))",
            interval_hours,
        )
        while True:
            try:
                await asyncio.sleep(interval_hours * 3600)
                results = await tasks.run_all()
                total = sum(results.values())
                if total > 0:
                    logger.info("Cleanup cycle complete: %s", results)
                else:
                    logger.debug("Cleanup cycle: nothing to clean")
            except asyncio.CancelledError:
                logger.info("Cleanup scheduler shutting down")
                break
            except Exception:
                logger.warning("Cleanup cycle failed", exc_info=True)

    return asyncio.create_task(_scheduler(), name="admin-cleanup-scheduler")
