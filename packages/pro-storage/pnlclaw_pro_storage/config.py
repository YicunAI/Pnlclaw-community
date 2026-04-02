"""Pro database configuration."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class ProDatabaseConfig(BaseSettings):
    """PostgreSQL connection settings for Pro storage.

    Reads from environment variables with ``PNLCLAW_PRO_`` prefix, e.g.
    ``PNLCLAW_PRO_DATABASE_URL``.
    """

    model_config = {"env_prefix": "PNLCLAW_PRO_"}

    database_url: str = Field(
        "postgresql+asyncpg://pnlclaw:pnlclaw@localhost:5432/pnlclaw",
        description="PostgreSQL async connection URL",
    )
    db_pool_size: int = Field(10, description="Connection pool size")
    db_max_overflow: int = Field(20, description="Max overflow connections")
    db_pool_recycle: int = Field(3600, description="Connection recycle time in seconds")
