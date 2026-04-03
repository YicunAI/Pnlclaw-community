"""Redis Pub/Sub for cross-worker WebSocket broadcasting.

When running with ``uvicorn --workers N``, market events from the exchange
WebSocket connection (which lives in one worker) need to reach WS clients
connected to other workers.  This module provides:

- ``publish(channel, data)``: publish an event to Redis
- ``start_subscriber(on_message)``: background task that listens for events
  and forwards them to the local ConnectionManager
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine

from app.core.redis import get_redis

logger = logging.getLogger(__name__)

_PUBSUB_CHANNEL = "pnlclaw:market_events"
_subscriber_task: asyncio.Task | None = None


async def publish(channel: str, data: dict[str, Any]) -> None:
    """Publish a market event to Redis Pub/Sub for cross-worker delivery."""
    redis = get_redis()
    if redis is None:
        return
    try:
        payload = json.dumps({"channel": channel, "data": data}, ensure_ascii=False, separators=(",", ":"))
        await redis.publish(_PUBSUB_CHANNEL, payload)
    except Exception:
        logger.debug("Redis publish failed", exc_info=True)


async def start_subscriber(
    on_message: Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]],
) -> None:
    """Start a background task that subscribes to Redis Pub/Sub and forwards
    events to the local WS broadcast function.

    ``on_message(channel, data)`` is called for each received event.
    """
    global _subscriber_task
    if _subscriber_task is not None and not _subscriber_task.done():
        return

    redis = get_redis()
    if redis is None:
        logger.info("Redis not available, cross-worker pub/sub disabled")
        return

    async def _listen() -> None:
        while True:
            try:
                pubsub = redis.pubsub()
                await pubsub.subscribe(_PUBSUB_CHANNEL)
                logger.info("Redis Pub/Sub subscriber started on %s", _PUBSUB_CHANNEL)
                async for raw_msg in pubsub.listen():
                    if raw_msg["type"] != "message":
                        continue
                    try:
                        payload = json.loads(raw_msg["data"])
                        channel = payload.get("channel", "")
                        data = payload.get("data", {})
                        await on_message(channel, data)
                    except Exception:
                        logger.debug("Pub/Sub message parse error", exc_info=True)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.warning("Redis Pub/Sub subscriber error, reconnecting in 2s", exc_info=True)
                await asyncio.sleep(2)

    _subscriber_task = asyncio.create_task(_listen(), name="redis-pubsub-subscriber")


async def stop_subscriber() -> None:
    """Stop the background subscriber task."""
    global _subscriber_task
    if _subscriber_task is not None:
        _subscriber_task.cancel()
        try:
            await _subscriber_task
        except asyncio.CancelledError:
            pass
        _subscriber_task = None
