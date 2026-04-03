"""Redis connection manager with health check and graceful degradation.

When Redis is unavailable the application continues to work — callers
get ``None`` from ``get_redis()`` and should fall through to the
exchange REST API directly.
"""

from __future__ import annotations

import logging
import os

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_redis_client: aioredis.Redis | None = None


async def init_redis() -> aioredis.Redis | None:
    """Create the shared Redis connection pool.  Returns ``None`` if
    Redis is not configured or unreachable (graceful degradation).
    """
    global _redis_client

    url = os.getenv("PNLCLAW_REDIS_URL", "").strip()
    if not url:
        logger.info("PNLCLAW_REDIS_URL not set — Redis caching disabled")
        return None

    try:
        client = aioredis.from_url(
            url,
            decode_responses=True,
            max_connections=50,
            socket_connect_timeout=3,
            socket_timeout=3,
            retry_on_timeout=True,
        )
        await client.ping()
        _redis_client = client
        logger.info("Redis connected: %s", url.split("@")[-1])
        return client
    except Exception:
        logger.warning("Redis unreachable at %s — caching disabled", url, exc_info=True)
        return None


async def close_redis() -> None:
    """Gracefully close the Redis connection pool."""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis connection closed")


def get_redis() -> aioredis.Redis | None:
    """Return the shared Redis client, or ``None`` if unavailable."""
    return _redis_client


async def redis_health_check() -> bool:
    """Quick ping for health monitoring."""
    if _redis_client is None:
        return False
    try:
        return await _redis_client.ping()
    except Exception:
        return False
