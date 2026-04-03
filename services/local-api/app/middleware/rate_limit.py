"""IP-based rate limiting middleware (pure ASGI, in-memory sliding window).

Enforces per-IP request rate limits to protect against abuse.  Uses a
lightweight sliding-window counter with automatic cleanup of stale entries.

Limits are intentionally generous for normal usage but strict enough to
block automated scraping or credential-stuffing attacks.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

GLOBAL_RATE_LIMIT = 120
GLOBAL_WINDOW_SECONDS = 60

AUTH_RATE_LIMIT = 20
AUTH_WINDOW_SECONDS = 60

_CLEANUP_INTERVAL = 300


class RateLimitMiddleware:
    """Pure ASGI middleware — tracks request counts per client IP."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._auth_requests: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.monotonic()

    def _get_client_ip(self, scope: Scope) -> str:
        headers = dict(scope.get("headers", []))
        forwarded = headers.get(b"x-forwarded-for", b"").decode()
        if forwarded:
            return forwarded.split(",")[0].strip()
        client = scope.get("client")
        if client:
            return client[0]
        return "unknown"

    def _is_rate_limited(self, ip: str, now: float, *, is_auth: bool) -> bool:
        store = self._auth_requests if is_auth else self._requests
        limit = AUTH_RATE_LIMIT if is_auth else GLOBAL_RATE_LIMIT
        window = AUTH_WINDOW_SECONDS if is_auth else GLOBAL_WINDOW_SECONDS

        cutoff = now - window
        entries = store[ip]
        while entries and entries[0] < cutoff:
            entries.pop(0)

        if len(entries) >= limit:
            return True

        entries.append(now)
        return False

    def _maybe_cleanup(self, now: float) -> None:
        if now - self._last_cleanup < _CLEANUP_INTERVAL:
            return
        self._last_cleanup = now
        for store in (self._requests, self._auth_requests):
            stale = [k for k, v in store.items() if not v or v[-1] < now - 600]
            for k in stale:
                del store[k]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        now = time.monotonic()
        self._maybe_cleanup(now)

        ip = self._get_client_ip(scope)
        path = scope.get("path", "")
        is_auth = path.startswith("/api/v1/auth") or path.startswith("/auth")

        if self._is_rate_limited(ip, now, is_auth=is_auth):
            await self._send_429(send, ip)
            return

        if is_auth and self._is_rate_limited(ip, now, is_auth=False):
            await self._send_429(send, ip)
            return

        await self.app(scope, receive, send)

    @staticmethod
    async def _send_429(send: Send, ip: str) -> None:
        body = b'{"detail":"Too many requests. Please slow down."}'
        headers: list[tuple[bytes, bytes]] = [
            (b"content-type", b"application/json"),
            (b"retry-after", b"60"),
            (b"content-length", str(len(body)).encode()),
        ]

        await send({"type": "http.response.start", "status": 429, "headers": headers})
        await send({"type": "http.response.body", "body": body})
