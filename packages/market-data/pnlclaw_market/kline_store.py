"""Redis-backed K-line cache using Sorted Sets.

Key schema:  ``kline:{exchange}:{market_type}:{symbol}:{interval}``
Score:       candle open timestamp (ms)
Value:       JSON-serialized KlineEvent

Sorted Sets guarantee O(log N) insert and O(log N + M) range queries,
which is ideal for timestamp-ordered K-line data.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis.asyncio as aioredis

from pnlclaw_types.market import KlineEvent

logger = logging.getLogger(__name__)

_TTL_SECONDS = 86400  # 24h default expiry per key
_MAX_CANDLES_PER_KEY = 2000


def _cache_key(exchange: str, market_type: str, symbol: str, interval: str) -> str:
    return f"kline:{exchange}:{market_type}:{symbol}:{interval}"


class KlineStore:
    """Thin wrapper around Redis Sorted Sets for K-line caching."""

    def __init__(self, redis: "aioredis.Redis", ttl: int = _TTL_SECONDS) -> None:
        self._r = redis
        self._ttl = ttl

    async def get(
        self,
        exchange: str,
        market_type: str,
        symbol: str,
        interval: str,
        *,
        since: int | None = None,
        limit: int = 500,
    ) -> list[KlineEvent]:
        """Retrieve cached K-lines, optionally filtered by ``since`` timestamp."""
        key = _cache_key(exchange, market_type, symbol, interval)
        try:
            if since is not None:
                raw = await self._r.zrangebyscore(key, min=since, max="+inf", start=0, num=limit)
            else:
                raw = await self._r.zrange(key, -limit, -1)
            return [KlineEvent.model_validate_json(item) for item in raw]
        except Exception:
            logger.warning("KlineStore.get failed for %s", key, exc_info=True)
            return []

    async def put(
        self,
        exchange: str,
        market_type: str,
        symbol: str,
        interval: str,
        candles: list[KlineEvent],
    ) -> int:
        """Bulk-write candles to cache.  Returns the number of *new* entries added."""
        if not candles:
            return 0
        key = _cache_key(exchange, market_type, symbol, interval)
        try:
            mapping: dict[str, float] = {}
            for c in candles:
                mapping[c.model_dump_json()] = float(c.timestamp)
            async with self._r.pipeline(transaction=False) as pipe:
                pipe.zadd(key, mapping)  # type: ignore[arg-type]
                pipe.expire(key, self._ttl)
                results = await pipe.execute()
            added = results[0] if results else 0
            await self._trim(key)
            return added or 0
        except Exception:
            logger.warning("KlineStore.put failed for %s", key, exc_info=True)
            return 0

    async def append(
        self,
        exchange: str,
        market_type: str,
        symbol: str,
        interval: str,
        candle: KlineEvent,
    ) -> None:
        """Append or update a single candle (real-time WS update).

        Uses pipeline to batch Redis operations into a single round-trip,
        preventing connection pool exhaustion under high-frequency WS events.
        """
        key = _cache_key(exchange, market_type, symbol, interval)
        try:
            ts = float(candle.timestamp)
            async with self._r.pipeline(transaction=False) as pipe:
                pipe.zremrangebyscore(key, ts, ts)
                pipe.zadd(key, {candle.model_dump_json(): ts})  # type: ignore[arg-type]
                pipe.expire(key, self._ttl)
                await pipe.execute()
        except Exception:
            logger.warning("KlineStore.append failed for %s", key, exc_info=True)

    async def count(self, exchange: str, market_type: str, symbol: str, interval: str) -> int:
        """Return the number of cached candles for a given key."""
        key = _cache_key(exchange, market_type, symbol, interval)
        try:
            return await self._r.zcard(key)
        except Exception:
            return 0

    async def _trim(self, key: str) -> None:
        """Keep only the most recent ``_MAX_CANDLES_PER_KEY`` candles."""
        try:
            total = await self._r.zcard(key)
            if total > _MAX_CANDLES_PER_KEY:
                await self._r.zremrangebyrank(key, 0, total - _MAX_CANDLES_PER_KEY - 1)
        except Exception:
            pass
