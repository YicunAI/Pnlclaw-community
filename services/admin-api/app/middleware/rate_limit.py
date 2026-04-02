"""In-memory rate limiter middleware for authentication endpoints.

Uses a simple sliding-window counter per IP. Suitable for single-instance
deployment. For multi-instance, replace with Redis-backed limiter.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_RATE_LIMITED_PREFIXES = (
    "/api/v1/auth/login",
    "/api/v1/auth/callback",
    "/api/v1/auth/verify-totp",
    "/api/v1/admin/2fa/enable",
)

_WINDOW_SECONDS = 60
_MAX_REQUESTS = 30
_TOTP_MAX_REQUESTS = 5

_ip_counters: dict[str, list[float]] = defaultdict(list)


def _clean_window(timestamps: list[float], now: float, window: float) -> list[float]:
    cutoff = now - window
    return [t for t in timestamps if t > cutoff]


class RateLimitMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that rate-limits sensitive endpoints by client IP."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        path = request.url.path

        is_rate_limited = any(path.startswith(p) for p in _RATE_LIMITED_PREFIXES)
        if not is_rate_limited:
            return await call_next(request)

        ip = self._client_ip(request)
        now = time.monotonic()

        key = f"{ip}:{path}"
        _ip_counters[key] = _clean_window(_ip_counters[key], now, _WINDOW_SECONDS)

        is_totp = "totp" in path or "2fa" in path
        limit = _TOTP_MAX_REQUESTS if is_totp else _MAX_REQUESTS

        if len(_ip_counters[key]) >= limit:
            retry_after = int(_WINDOW_SECONDS - (now - _ip_counters[key][0]))
            return JSONResponse(
                status_code=429,
                content={
                    "data": None,
                    "meta": None,
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": "Too many requests. Please try again later.",
                    },
                },
                headers={"Retry-After": str(max(1, retry_after))},
            )

        _ip_counters[key].append(now)
        return await call_next(request)

    @staticmethod
    def _client_ip(request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        if request.client:
            return request.client.host
        return "unknown"
