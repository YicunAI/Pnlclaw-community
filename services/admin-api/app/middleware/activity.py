"""Activity tracking middleware -- logs authenticated user API calls."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Buffer settings for periodic flush
_BUFFER_FLUSH_INTERVAL = 10.0  # seconds
_BUFFER_MAX_SIZE = 100


class ActivityTrackingMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that logs authenticated user API calls.

    Uses a memory buffer with periodic flush for performance. Instead of
    writing to the database on every request, entries are buffered and
    flushed every few seconds or when the buffer reaches a threshold.
    """

    def __init__(self, app: Any) -> None:
        super().__init__(app)
        self._buffer: list[dict[str, Any]] = []
        self._buffer_lock = asyncio.Lock()
        self._flush_task: asyncio.Task[None] | None = None

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000

        # Only track authenticated requests
        user = getattr(request.state, "user", None)
        if user is not None:
            entry = {
                "user_id": user.id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "ip_address": self._client_ip(request),
                "user_agent": request.headers.get("User-Agent", ""),
            }

            async with self._buffer_lock:
                self._buffer.append(entry)
                # Start flush task if not running
                if self._flush_task is None or self._flush_task.done():
                    self._flush_task = asyncio.create_task(
                        self._periodic_flush(),
                        name="activity-flush",
                    )
                # Flush immediately if buffer is full
                if len(self._buffer) >= _BUFFER_MAX_SIZE:
                    await self._flush()

        return response

    async def _periodic_flush(self) -> None:
        """Periodically flush the buffer to the database."""
        try:
            while True:
                await asyncio.sleep(_BUFFER_FLUSH_INTERVAL)
                async with self._buffer_lock:
                    if self._buffer:
                        await self._flush()
                    else:
                        # No entries to flush, stop the task
                        return
        except asyncio.CancelledError:
            # Final flush on cancellation
            async with self._buffer_lock:
                if self._buffer:
                    await self._flush()

    async def _flush(self) -> None:
        """Flush buffered entries to the activity log repository."""
        if not self._buffer:
            return

        entries = list(self._buffer)
        self._buffer.clear()

        try:
            from app.core.dependencies import get_activity_repo

            repo = get_activity_repo()
            if repo is None:
                return

            for entry in entries:
                try:
                    await repo.log(
                        user_id=uuid.UUID(entry["user_id"]),
                        event_type=f"{entry['method']} {entry['path']}",
                        ip_address=entry.get("ip_address"),
                        user_agent=entry.get("user_agent"),
                        path=entry.get("path"),
                        method=entry.get("method"),
                    )
                except Exception:
                    logger.debug("Failed to write activity entry", exc_info=True)
        except Exception:
            logger.debug("Activity flush failed", exc_info=True)

    @staticmethod
    def _client_ip(request: Request) -> str:
        """Extract client IP from request."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"
