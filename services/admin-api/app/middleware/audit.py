"""Admin audit middleware -- logs admin actions to the audit table."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Paths that trigger audit logging (admin-facing mutation endpoints)
_AUDITABLE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_AUDITABLE_PREFIXES = (
    "/api/v1/admin/",
    "/api/v1/auth/logout",
)


class AdminAuditMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that automatically logs admin actions to the admin_audit table.

    For any request matching an auditable path and method, extracts the admin user
    from request state (set by the auth dependency), then logs:
    - HTTP method
    - Request path
    - Target resource (parsed from path)
    - Response status
    - Duration
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        # Skip non-auditable requests early
        if request.method not in _AUDITABLE_METHODS:
            return await call_next(request)

        path = request.url.path
        if not any(path.startswith(prefix) for prefix in _AUDITABLE_PREFIXES):
            return await call_next(request)

        start = time.monotonic()
        response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000

        # Try to log the action asynchronously (best-effort)
        try:
            await self._log_action(request, path, response.status_code, duration_ms)
        except Exception:
            logger.debug("Admin audit middleware log failed", exc_info=True)

        return response

    async def _log_action(
        self,
        request: Request,
        path: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        """Write audit entry if an authenticated admin user is available."""
        user = getattr(request.state, "user", None)
        if user is None:
            return

        # Only audit admin/operator actions
        role = getattr(user, "role", "user")
        if role not in ("admin", "operator"):
            return

        from app.core.dependencies import get_admin_audit_repo

        audit_repo = get_admin_audit_repo()
        if audit_repo is None:
            return

        # Parse target from path segments
        # e.g. /api/v1/admin/users/abc-123/ban -> target_user_id = abc-123
        target_user_id: str | None = None
        parts = path.strip("/").split("/")
        if "users" in parts:
            idx = parts.index("users")
            if idx + 1 < len(parts):
                candidate = parts[idx + 1]
                # Skip non-ID segments like "bulk-action" or "export"
                if candidate not in ("bulk-action", "export"):
                    target_user_id = candidate

        action = f"{request.method} {path}"

        details: dict[str, Any] = {
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
        }

        try:
            await audit_repo.log(
                admin_user_id=uuid.UUID(user.id),
                action=action,
                target_user_id=uuid.UUID(target_user_id) if target_user_id else None,
                details=details,
            )
        except Exception:
            logger.debug("Failed to write admin audit entry", exc_info=True)
