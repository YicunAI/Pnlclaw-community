"""Admin API configuration."""

from __future__ import annotations

from pnlclaw_pro_storage.config import ProDatabaseConfig


class AdminAPIConfig(ProDatabaseConfig):
    """Configuration for the Admin API service.

    Inherits all PostgreSQL connection settings from ProDatabaseConfig
    and adds HTTP-specific configuration.
    """

    host: str = "0.0.0.0"
    port: int = 8001
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
    ]
    debug: bool = False
