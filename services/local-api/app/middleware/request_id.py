"""Request ID middleware.

Assigns a UUID to each incoming request, binds it to structlog context,
stores it on ``request.state``, and adds it as ``X-Request-ID`` response header.

If the request already carries an ``X-Request-ID`` header, that value is reused.
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from pnlclaw_core.logging import bind_request_id


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Inject a unique request ID into every request/response cycle."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Reuse incoming header or generate a new UUID
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex

        # Store on request state (used by error handler and routes)
        request.state.request_id = request_id

        # Bind to structlog context for the duration of this request
        bind_request_id(request_id)

        response = await call_next(request)

        # Echo back in response header
        response.headers["X-Request-ID"] = request_id

        return response
