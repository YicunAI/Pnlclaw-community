"""Dependency injection for admin-api service instances.

Each service is created once at startup (via lifespan) and injected into
route handlers through FastAPI's ``Depends`` mechanism.  During testing the
instances can be overridden via ``app.dependency_overrides``.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Request
from pydantic import BaseModel

from pnlclaw_types.common import Pagination, ResponseMeta
from pnlclaw_types.errors import ErrorCode, PnLClawError

# ---------------------------------------------------------------------------
# Singleton holders -- populated during lifespan startup
# ---------------------------------------------------------------------------

_postgres_manager: Any | None = None
_user_repo: Any | None = None
_oauth_repo: Any | None = None
_session_repo: Any | None = None
_activity_repo: Any | None = None
_admin_audit_repo: Any | None = None
_login_history_repo: Any | None = None
_user_tag_repo: Any | None = None
_admin_note_repo: Any | None = None
_jwt_manager: Any | None = None
_session_manager: Any | None = None
_totp_manager: Any | None = None
_geoip_resolver: Any | None = None
_device_parser: Any | None = None
_oauth_providers: dict[str, Any] | None = None
_auth_config: Any | None = None

# ---------------------------------------------------------------------------
# Setters -- called from lifespan
# ---------------------------------------------------------------------------


def set_postgres_manager(manager: Any) -> None:
    global _postgres_manager
    _postgres_manager = manager


def set_user_repo(repo: Any) -> None:
    global _user_repo
    _user_repo = repo


def set_oauth_repo(repo: Any) -> None:
    global _oauth_repo
    _oauth_repo = repo


def set_session_repo(repo: Any) -> None:
    global _session_repo
    _session_repo = repo


def set_activity_repo(repo: Any) -> None:
    global _activity_repo
    _activity_repo = repo


def set_admin_audit_repo(repo: Any) -> None:
    global _admin_audit_repo
    _admin_audit_repo = repo


def set_login_history_repo(repo: Any) -> None:
    global _login_history_repo
    _login_history_repo = repo


def set_user_tag_repo(repo: Any) -> None:
    global _user_tag_repo
    _user_tag_repo = repo


def set_admin_note_repo(repo: Any) -> None:
    global _admin_note_repo
    _admin_note_repo = repo


def set_jwt_manager(manager: Any) -> None:
    global _jwt_manager
    _jwt_manager = manager


def set_session_manager(manager: Any) -> None:
    global _session_manager
    _session_manager = manager


def set_totp_manager(manager: Any) -> None:
    global _totp_manager
    _totp_manager = manager


def set_geoip_resolver(resolver: Any) -> None:
    global _geoip_resolver
    _geoip_resolver = resolver


def set_device_parser(parser: Any) -> None:
    global _device_parser
    _device_parser = parser


def set_oauth_providers(providers: dict[str, Any]) -> None:
    global _oauth_providers
    _oauth_providers = providers


def set_auth_config(config: Any) -> None:
    global _auth_config
    _auth_config = config


# ---------------------------------------------------------------------------
# Getters -- FastAPI dependency callables
# ---------------------------------------------------------------------------


def get_postgres_manager() -> Any:
    """Return the AsyncPostgresManager instance."""
    return _postgres_manager


def get_user_repo() -> Any:
    """Return the UserRepository instance."""
    return _user_repo


def get_oauth_repo() -> Any:
    """Return the OAuthAccountRepository instance."""
    return _oauth_repo


def get_session_repo() -> Any:
    """Return the SessionRepository instance."""
    return _session_repo


def get_activity_repo() -> Any:
    """Return the ActivityLogRepository instance."""
    return _activity_repo


def get_admin_audit_repo() -> Any:
    """Return the AdminAuditRepository instance."""
    return _admin_audit_repo


def get_login_history_repo() -> Any:
    """Return the LoginHistoryRepository instance."""
    return _login_history_repo


def get_user_tag_repo() -> Any:
    """Return the UserTagRepository instance."""
    return _user_tag_repo


def get_admin_note_repo() -> Any:
    """Return the AdminNoteRepository instance."""
    return _admin_note_repo


def get_jwt_manager() -> Any:
    """Return the JWTManager instance."""
    return _jwt_manager


def get_session_manager() -> Any:
    """Return the SessionManager instance."""
    return _session_manager


def get_totp_manager() -> Any:
    """Return the TOTPManager instance."""
    return _totp_manager


def get_geoip_resolver() -> Any:
    """Return the GeoIPResolver instance."""
    return _geoip_resolver


def get_device_parser() -> Any:
    """Return the DeviceParser instance."""
    return _device_parser


def get_oauth_providers() -> dict[str, Any]:
    """Return the dict of configured OAuth providers."""
    return _oauth_providers or {}


def get_auth_config() -> Any:
    """Return the AuthConfig instance."""
    return _auth_config


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------


def build_response_meta(
    request: Request,
    pagination: Pagination | None = None,
) -> ResponseMeta:
    """Build API response metadata with request correlation id."""
    request_id = getattr(request.state, "request_id", None)
    return ResponseMeta(request_id=request_id, pagination=pagination)


# ---------------------------------------------------------------------------
# Authenticated user model
# ---------------------------------------------------------------------------


class AuthenticatedUser(BaseModel):
    """Represents an authenticated user extracted from a valid JWT."""

    id: str
    email: str
    display_name: str = ""
    role: str = "user"
    session_id: str = ""


# ---------------------------------------------------------------------------
# Auth dependencies -- used by route handlers via Depends()
# ---------------------------------------------------------------------------


async def require_auth(request: Request) -> AuthenticatedUser:
    """Extract and validate JWT from Authorization header.

    Checks:
    1. Authorization header is present with Bearer scheme
    2. JWT is valid and not expired
    3. Session referenced in the JWT has not been revoked

    Raises PnLClawError(AUTHENTICATION_ERROR) on failure.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise PnLClawError(
            code=ErrorCode.AUTHENTICATION_ERROR,
            message="Missing or invalid Authorization header",
        )

    token = auth_header[len("Bearer "):]
    jwt_mgr = get_jwt_manager()
    if jwt_mgr is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Authentication service is not available",
        )

    try:
        payload = jwt_mgr.decode_access_token(token)
    except Exception as exc:
        raise PnLClawError(
            code=ErrorCode.AUTHENTICATION_ERROR,
            message="Invalid or expired access token",
        ) from exc

    user_id: str = payload.get("sub", "")
    jti: str = payload.get("jti", "")
    if not user_id:
        raise PnLClawError(
            code=ErrorCode.AUTHENTICATION_ERROR,
            message="Invalid token payload",
        )

    # Check session not revoked via raw SessionRepository
    if jti:
        session_repo = get_session_repo()
        if session_repo is not None:
            session = await session_repo.get_by_jti(jti)
            if session is not None and session.revoked_at is not None:
                raise PnLClawError(
                    code=ErrorCode.AUTHENTICATION_ERROR,
                    message="Session has been revoked",
                )

    user = AuthenticatedUser(
        id=user_id,
        email=payload.get("email", ""),
        display_name=payload.get("name", ""),
        role=payload.get("role", "user"),
        session_id=jti,
    )

    # Attach to request state for middleware access
    request.state.user = user
    return user


async def require_admin(
    user: AuthenticatedUser = Depends(require_auth),
) -> AuthenticatedUser:
    """Require that the authenticated user has admin or operator role.

    Raises PnLClawError(PERMISSION_DENIED) if the user role is insufficient.
    """
    if user.role not in ("admin", "operator"):
        raise PnLClawError(
            code=ErrorCode.PERMISSION_DENIED,
            message="Admin or operator role required",
        )
    return user
