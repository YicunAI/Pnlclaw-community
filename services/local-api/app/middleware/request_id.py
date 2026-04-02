"""Request ID middleware (pure ASGI for minimal overhead).

Assigns a UUID to each incoming request, binds it to structlog context,
stores it on ``request.state``, and adds it as ``X-Request-ID`` response header.

If the request already carries an ``X-Request-ID`` header, that value is reused.
"""

from __future__ import annotations

import uuid
from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

from pnlclaw_core.logging import bind_request_id


class RequestIDMiddleware:
    """Pure ASGI middleware — avoids BaseHTTPMiddleware thread overhead."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        request_id = headers.get(b"x-request-id", b"").decode() or uuid.uuid4().hex

        scope.setdefault("state", {})["request_id"] = request_id
        bind_request_id(request_id)

        if scope["type"] == "http":

            async def send_with_id(message: Any) -> None:
                if message["type"] == "http.response.start":
                    h = list(message.get("headers", []))
                    h.append((b"x-request-id", request_id.encode()))
                    message["headers"] = h
                await send(message)

            await self.app(scope, receive, send_with_id)
        else:
            await self.app(scope, receive, send)
