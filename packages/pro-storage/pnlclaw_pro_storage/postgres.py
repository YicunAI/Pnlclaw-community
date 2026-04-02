"""Async PostgreSQL manager using SQLAlchemy async engine.

Parallels the community ``AsyncSQLiteManager`` interface but targets
PostgreSQL via asyncpg for multi-user concurrent access.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import text

from pnlclaw_pro_storage.config import ProDatabaseConfig

logger = logging.getLogger(__name__)

# Alembic config path relative to this package
_ALEMBIC_INI = Path(__file__).parent / "alembic.ini"


class ProStorageError(Exception):
    """Base exception for Pro storage operations."""


class ProConnectionError(ProStorageError):
    """Failed to establish or maintain a database connection."""


class AsyncPostgresManager:
    """Async PostgreSQL manager with connection pooling.

    Args:
        config: Pro database configuration.
    """

    def __init__(self, config: ProDatabaseConfig | None = None) -> None:
        self._config = config or ProDatabaseConfig()
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    @property
    def is_connected(self) -> bool:
        return self._engine is not None

    async def connect(self, run_migrations: bool = True) -> None:
        """Create the async engine and optionally run Alembic migrations."""
        if self._engine is not None:
            return

        self._engine = create_async_engine(
            self._config.database_url,
            pool_size=self._config.db_pool_size,
            max_overflow=self._config.db_max_overflow,
            pool_recycle=self._config.db_pool_recycle,
            pool_pre_ping=True,
            echo=False,
        )

        if run_migrations:
            await self._run_migrations()

        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        logger.info("Pro PostgreSQL connected (pool_size=%d)", self._config.db_pool_size)

    async def close(self) -> None:
        """Dispose the engine and release all connections."""
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("Pro PostgreSQL disconnected")

    async def _run_migrations(self) -> None:
        """Run Alembic migrations to head."""
        import asyncio
        from concurrent.futures import ThreadPoolExecutor

        def _run_alembic() -> None:
            from alembic.config import Config
            from alembic import command

            alembic_cfg = Config(str(_ALEMBIC_INI))
            # Override sqlalchemy.url with the actual URL (swap asyncpg → psycopg for sync)
            sync_url = self._config.database_url.replace(
                "postgresql+asyncpg", "postgresql+psycopg"
            )
            alembic_cfg.set_main_option("sqlalchemy.url", sync_url)
            command.upgrade(alembic_cfg, "head")

        loop = asyncio.get_running_loop()
        with ThreadPoolExecutor(max_workers=1) as pool:
            await loop.run_in_executor(pool, _run_alembic)
        logger.info("Pro database migrations applied")

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield an async session with automatic commit/rollback."""
        if self._session_factory is None:
            raise ProConnectionError("Database not connected. Call connect() first.")

        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    async def health_check(self) -> bool:
        """Return True if the database is reachable."""
        if self._engine is None:
            return False
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    async def __aenter__(self) -> AsyncPostgresManager:
        await self.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
