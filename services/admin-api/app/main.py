"""PnLClaw Admin API -- FastAPI entrypoint with lifespan management."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.admin_2fa import router as admin_2fa_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router
from app.api.v1.invitations import router as invitations_router
from app.api.v1.tags import router as tags_router
from app.api.v1.users import router as users_router, sessions_router
from app.core.config import AdminAPIConfig
from app.core.dependencies import (
    set_activity_repo,
    set_admin_audit_repo,
    set_admin_note_repo,
    set_auth_config,
    set_device_parser,
    set_geoip_resolver,
    set_jwt_manager,
    set_login_history_repo,
    set_oauth_providers,
    set_oauth_repo,
    set_postgres_manager,
    set_session_manager,
    set_session_repo,
    set_totp_manager,
    set_user_repo,
    set_user_tag_repo,
)
from app.middleware.activity import ActivityTrackingMiddleware
from app.middleware.audit import AdminAuditMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from pnlclaw_types.errors import PnLClawError

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s: %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Adapters: bridge pro-storage SessionRepository → pro-auth Protocols
# ---------------------------------------------------------------------------

class _SessionRepoAdapter:
    """Wraps pro-storage SessionRepository to satisfy pro-auth's SessionRepository Protocol."""

    def __init__(self, repo: Any) -> None:
        self._repo = repo

    async def create(
        self, user_id: str, jti: str, ip_address: str | None,
        user_agent: str | None, expires_at: Any,
    ) -> Any:
        import uuid as _uuid
        session = await self._repo.create(
            user_id=_uuid.UUID(user_id), jti=jti,
            ip_address=ip_address, user_agent=user_agent, expires_at=expires_at,
        )
        return session.id

    async def get_by_jti(self, jti: str) -> dict | None:
        session = await self._repo.get_by_jti(jti)
        if session is None:
            return None
        return {
            "id": session.id, "user_id": str(session.user_id), "jti": session.jti,
            "ip_address": session.ip_address, "user_agent": session.user_agent,
            "revoked_at": session.revoked_at, "expires_at": session.expires_at,
            "role": getattr(session, "role", "user"),
        }

    async def get_by_id(self, session_id: Any) -> dict | None:
        return await self.get_by_jti("")  # not used in practice

    async def revoke(self, jti: str) -> None:
        session = await self._repo.get_by_jti(jti)
        if session is not None:
            await self._repo.revoke(session.id)

    async def revoke_all_for_user(self, user_id: str) -> int:
        import uuid as _uuid
        return await self._repo.revoke_all_for_user(_uuid.UUID(user_id))


class _RefreshTokenRepoAdapter:
    """Wraps pro-storage SessionRepository refresh methods to satisfy pro-auth's RefreshTokenRepository Protocol."""

    def __init__(self, repo: Any) -> None:
        self._repo = repo

    async def create(self, session_id: Any, token_hash: str, expires_at: Any) -> None:
        await self._repo.create_refresh_token(
            session_id=session_id, token_hash=token_hash, expires_at=expires_at,
        )

    async def get_by_hash(self, token_hash: str) -> dict | None:
        rt = await self._repo.get_refresh_token(token_hash)
        if rt is None:
            return None
        return {
            "id": rt.id, "session_id": rt.session_id, "token_hash": rt.token_hash,
            "used_at": rt.used_at, "revoked_at": getattr(rt, "revoked_at", None),
            "expires_at": rt.expires_at,
        }

    async def mark_used(self, token_hash: str) -> None:
        await self._repo.use_refresh_token(token_hash)

    async def revoke_all_for_session(self, session_id: Any) -> None:
        pass  # pro-storage doesn't expose this; handled by session revocation

    async def revoke_all_for_user(self, user_id: str) -> None:
        pass  # pro-storage doesn't expose this; handled by session revocation


def _build_oauth_providers(auth_config: Any) -> dict[str, Any]:
    """Build configured OAuth providers from AuthConfig."""
    from pnlclaw_pro_auth.oauth import (
        GitHubOAuthProvider,
        GoogleOAuthProvider,
        TwitterOAuthProvider,
    )

    providers: dict[str, Any] = {}
    redirect_base = auth_config.oauth_redirect_base_url

    if auth_config.google_client_id and auth_config.google_client_secret:
        providers["google"] = GoogleOAuthProvider(
            client_id=auth_config.google_client_id,
            client_secret=auth_config.google_client_secret,
        )

    if auth_config.github_client_id and auth_config.github_client_secret:
        providers["github"] = GitHubOAuthProvider(
            client_id=auth_config.github_client_id,
            client_secret=auth_config.github_client_secret,
        )

    if auth_config.twitter_client_id and auth_config.twitter_client_secret:
        providers["twitter"] = TwitterOAuthProvider(
            client_id=auth_config.twitter_client_id,
            client_secret=auth_config.twitter_client_secret,
        )

    return providers


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup and shutdown hooks."""
    from pnlclaw_pro_auth import AuthConfig, JWTManager, SessionManager, TOTPManager
    from pnlclaw_pro_auth.device_parser import DeviceParser
    from pnlclaw_pro_auth.geoip import GeoIPResolver
    from pnlclaw_pro_auth.oauth import (
        GitHubOAuthProvider,
        GoogleOAuthProvider,
        TwitterOAuthProvider,
    )
    from pnlclaw_pro_storage.postgres import AsyncPostgresManager
    from pnlclaw_pro_storage.repositories import (
        ActivityLogRepository,
        AdminAuditRepository,
        AdminNoteRepository,
        LoginHistoryRepository,
        OAuthAccountRepository,
        SessionRepository,
        UserRepository,
        UserTagRepository,
    )

    config = AdminAPIConfig()

    # --- Database ---
    pg_manager = AsyncPostgresManager(config)
    await pg_manager.connect(run_migrations=False)
    set_postgres_manager(pg_manager)
    logger.info("PostgreSQL connected")

    # --- Auth Config ---
    auth_config = AuthConfig()
    set_auth_config(auth_config)

    # --- JWT ---
    jwt_manager = JWTManager(
        secret_key=auth_config.jwt_secret,
        algorithm=auth_config.jwt_algorithm,
    )
    set_jwt_manager(jwt_manager)

    # --- OAuth Providers ---
    oauth_providers = _build_oauth_providers(auth_config)
    set_oauth_providers(oauth_providers)
    logger.info("OAuth providers configured: %s", list(oauth_providers.keys()))

    # --- Repositories ---
    user_repo = UserRepository(pg_manager)
    set_user_repo(user_repo)

    oauth_repo = OAuthAccountRepository(pg_manager)
    set_oauth_repo(oauth_repo)

    session_repo = SessionRepository(pg_manager)
    set_session_repo(session_repo)

    activity_repo = ActivityLogRepository(pg_manager)
    set_activity_repo(activity_repo)

    admin_audit_repo = AdminAuditRepository(pg_manager)
    set_admin_audit_repo(admin_audit_repo)

    login_history_repo = LoginHistoryRepository(pg_manager)
    set_login_history_repo(login_history_repo)

    user_tag_repo = UserTagRepository(pg_manager)
    set_user_tag_repo(user_tag_repo)

    admin_note_repo = AdminNoteRepository(pg_manager)
    set_admin_note_repo(admin_note_repo)

    # --- Session Manager ---
    # pro-auth SessionManager expects Protocol-based session_repo/refresh_repo.
    # pro-storage SessionRepository handles both, so we create thin adapters.
    session_manager = SessionManager(
        jwt_manager=jwt_manager,
        session_repo=_SessionRepoAdapter(session_repo),
        refresh_repo=_RefreshTokenRepoAdapter(session_repo),
        config=auth_config,
    )
    set_session_manager(session_manager)

    # --- TOTP Manager ---
    totp_manager = TOTPManager()
    set_totp_manager(totp_manager)

    # --- GeoIP + Device Parser ---
    geoip_resolver = GeoIPResolver()
    set_geoip_resolver(geoip_resolver)

    device_parser = DeviceParser()
    set_device_parser(device_parser)

    # --- Background Cleanup ---
    from app.tasks.cleanup import start_cleanup_scheduler

    cleanup_task = start_cleanup_scheduler(
        session_repo=session_repo,
        user_repo=user_repo,
        pg_manager=pg_manager,
        interval_hours=1,
    )

    logger.info("PnLClaw Admin API started")

    yield

    # --- Shutdown ---
    if cleanup_task is not None:
        cleanup_task.cancel()
        logger.info("Cleanup scheduler cancelled")

    set_postgres_manager(None)
    set_user_repo(None)
    set_oauth_repo(None)
    set_session_repo(None)
    set_activity_repo(None)
    set_admin_audit_repo(None)
    set_login_history_repo(None)
    set_user_tag_repo(None)
    set_admin_note_repo(None)
    set_jwt_manager(None)
    set_session_manager(None)
    set_totp_manager(None)
    set_geoip_resolver(None)
    set_device_parser(None)
    set_oauth_providers({})
    set_auth_config(None)

    await pg_manager.close()
    logger.info("PnLClaw Admin API shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    config = AdminAPIConfig()

    app = FastAPI(
        title="PnLClaw Admin API",
        description="Pro admin API service for user management and analytics",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Security headers middleware
    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        return response

    # Middleware stack: added in reverse order (last added = outermost).
    # CORS must be outermost so every response (including 429 / 401) gets
    # proper Access-Control-* headers and OPTIONS preflight is handled.
    app.add_middleware(ActivityTrackingMiddleware)
    app.add_middleware(AdminAuditMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
        max_age=3600,
    )

    # Exception handler for PnLClawError
    @app.exception_handler(PnLClawError)
    async def pnlclaw_error_handler(request: Request, exc: PnLClawError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={"data": None, "meta": None, "error": exc.to_dict()},
        )

    # Generic exception handler — never expose internal details
    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "data": None,
                "meta": None,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An internal error occurred",
                },
            },
        )

    # Request validation error handler
    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "data": None,
                "meta": None,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": exc.errors(),
                },
            },
        )

    # Routers
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1")
    app.include_router(sessions_router, prefix="/api/v1")
    app.include_router(tags_router, prefix="/api/v1")
    app.include_router(invitations_router, prefix="/api/v1")
    app.include_router(admin_2fa_router, prefix="/api/v1")
    app.include_router(analytics_router, prefix="/api/v1")

    return app


app = create_app()
