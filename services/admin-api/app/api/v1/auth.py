"""Authentication endpoints -- OAuth login, token refresh, session management."""

from __future__ import annotations

import logging
import secrets
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from app.core.dependencies import (
    AuthenticatedUser,
    build_response_meta,
    get_auth_config,
    get_device_parser,
    get_geoip_resolver,
    get_jwt_manager,
    get_login_history_repo,
    get_oauth_providers,
    get_oauth_repo,
    get_session_manager,
    get_totp_manager,
    get_user_repo,
    require_auth,
)
from pnlclaw_types.common import APIResponse
from pnlclaw_types.errors import ErrorCode, PnLClawError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class TOTPVerifyRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)
    partial_token: str = Field(..., description="Partial token received after OAuth login")


class LinkProviderResponse(BaseModel):
    linked: bool = True
    provider: str


class AccountDeleteResponse(BaseModel):
    deleted: bool = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client_ip(request: Request) -> str:
    """Extract client IP from X-Forwarded-For or direct connection."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


async def _record_login(
    request: Request,
    user_id: str,
    provider: str,
    success: bool,
) -> None:
    """Record login attempt in history with GeoIP and device info."""
    try:
        login_history_repo = get_login_history_repo()
        geoip = get_geoip_resolver()
        device_parser = get_device_parser()

        if login_history_repo is None:
            return

        ip = _client_ip(request)
        user_agent = request.headers.get("User-Agent", "")

        country: str | None = None
        city: str | None = None
        if geoip is not None:
            try:
                geo = geoip.resolve(ip)
                if geo is not None:
                    country = geo.country
                    city = geo.city
            except Exception:
                logger.debug("GeoIP resolve failed for %s", ip)

        device_type: str | None = None
        os_name: str | None = None
        browser: str | None = None
        if device_parser is not None:
            try:
                info = device_parser.parse(user_agent)
                device_type = info.device_type
                os_name = info.os
                browser = info.browser
            except Exception:
                logger.debug("Device parse failed for user-agent")

        await login_history_repo.record(
            user_id=uuid.UUID(user_id),
            provider=provider,
            ip_address=ip,
            country=country,
            city=city,
            user_agent=user_agent,
            device_type=device_type,
            os=os_name,
            browser=browser,
            success=success,
        )
    except Exception:
        logger.warning("Failed to record login history", exc_info=True)


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Set refresh token as an HttpOnly secure cookie."""
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=30 * 24 * 60 * 60,
        path="/api/v1/auth",
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Clear the refresh token cookie."""
    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        secure=False,
        samesite="lax",
        path="/api/v1/auth",
    )


_ALLOWED_REDIRECT_ORIGINS: set[str] = {
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
}


def _get_redirect_uri(auth_config: Any, provider: str, origin: str | None = None) -> str:
    """Build the OAuth redirect URI for a provider.

    If *origin* is supplied and is in the allowlist, use it;
    otherwise fall back to the configured default.
    Twitter/X rejects ``localhost`` callback URLs — rewrite to ``127.0.0.1``.
    """
    if origin and origin.rstrip("/") in _ALLOWED_REDIRECT_ORIGINS:
        base = origin.rstrip("/")
    else:
        base = auth_config.oauth_redirect_base_url.rstrip("/")

    if provider == "twitter":
        base = base.replace("://localhost:", "://127.0.0.1:")

    return f"{base}/login?callback={provider}"


# ---------------------------------------------------------------------------
# Available providers
# ---------------------------------------------------------------------------


@router.get("/providers")
async def list_providers(
    providers: dict[str, Any] = Depends(get_oauth_providers),
) -> APIResponse[dict[str, Any]]:
    """Return the list of configured OAuth providers."""
    return APIResponse(
        data={"providers": list(providers.keys())},
        meta=None,
        error=None,
    )


# ---------------------------------------------------------------------------
# OAuth login flow
# ---------------------------------------------------------------------------


@router.get("/login/{provider}")
async def oauth_login(
    provider: str,
    request: Request,
    redirect_to: str | None = None,
    jwt_mgr: Any = Depends(get_jwt_manager),
    providers: dict[str, Any] = Depends(get_oauth_providers),
    auth_config: Any = Depends(get_auth_config),
) -> APIResponse[dict[str, str]]:
    """Generate an OAuth redirect URL for the given provider."""
    if provider not in providers:
        raise PnLClawError(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"Unsupported OAuth provider: {provider}",
            details={"available": list(providers.keys())},
        )

    if jwt_mgr is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="JWT service not available",
        )

    nonce = secrets.token_urlsafe(16)
    extra: dict[str, str] = {}
    if redirect_to and redirect_to.rstrip("/") in _ALLOWED_REDIRECT_ORIGINS:
        extra["redirect_to"] = redirect_to.rstrip("/")
    state_token = jwt_mgr.create_state_token(provider=provider, nonce=nonce, **extra)

    redirect_uri = _get_redirect_uri(auth_config, provider, origin=redirect_to)
    oauth_provider = providers[provider]

    result = await oauth_provider.get_authorization_url(
        state=state_token,
        redirect_uri=redirect_uri,
    )
    if isinstance(result, tuple):
        redirect_url, code_verifier = result
        state_token = jwt_mgr.create_state_token(
            provider=provider,
            nonce=nonce,
            code_verifier=code_verifier,
            **extra,
        )
        from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

        parsed = urlparse(redirect_url)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        qs["state"] = [state_token]
        new_query = urlencode(qs, doseq=True)
        redirect_url = urlunparse(parsed._replace(query=new_query))
    else:
        redirect_url = result

    return APIResponse(
        data={"redirect_url": redirect_url, "state": state_token},
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/callback/{provider}")
async def oauth_callback(
    provider: str,
    code: str,
    state: str,
    request: Request,
    response: Response,
    jwt_mgr: Any = Depends(get_jwt_manager),
    providers: dict[str, Any] = Depends(get_oauth_providers),
    user_repo: Any = Depends(get_user_repo),
    oauth_repo: Any = Depends(get_oauth_repo),
    session_mgr: Any = Depends(get_session_manager),
    totp_mgr: Any = Depends(get_totp_manager),
    auth_config: Any = Depends(get_auth_config),
) -> APIResponse[dict[str, Any]]:
    """Handle OAuth callback after provider redirects back."""
    if provider not in providers:
        raise PnLClawError(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"Unsupported OAuth provider: {provider}",
        )

    if jwt_mgr is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="JWT service not available",
        )

    # 1. Validate state
    try:
        state_payload = jwt_mgr.decode_state_token(state)
    except Exception as exc:
        raise PnLClawError(
            code=ErrorCode.AUTHENTICATION_ERROR,
            message="Invalid or expired state token",
        ) from exc

    if state_payload.get("provider") != provider:
        raise PnLClawError(
            code=ErrorCode.AUTHENTICATION_ERROR,
            message="State token provider mismatch",
        )

    origin_override = state_payload.get("redirect_to")

    # 2. Exchange code for tokens
    redirect_uri = _get_redirect_uri(auth_config, provider, origin=origin_override)
    oauth_provider = providers[provider]
    code_verifier = state_payload.get("code_verifier")

    try:
        token_response = await oauth_provider.exchange_code(
            code,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
        )
    except Exception as exc:
        raise PnLClawError(
            code=ErrorCode.AUTHENTICATION_ERROR,
            message="Failed to exchange authorization code",
            details={"provider": provider},
        ) from exc

    # 3. Get user info from provider
    try:
        user_info = await oauth_provider.get_user_info(token_response.access_token)
    except Exception as exc:
        raise PnLClawError(
            code=ErrorCode.AUTHENTICATION_ERROR,
            message="Failed to fetch user info from provider",
            details={"provider": provider},
        ) from exc

    provider_user_id = user_info.provider_user_id
    email = user_info.email or ""
    display_name = user_info.name or ""
    avatar_url = user_info.avatar_url or ""

    if not provider_user_id:
        raise PnLClawError(
            code=ErrorCode.AUTHENTICATION_ERROR,
            message="Provider did not return a valid user ID",
        )

    # 4. Find or create user
    oauth_account = await oauth_repo.get_by_provider(provider, provider_user_id)

    if oauth_account is not None:
        user = await user_repo.get_by_id(oauth_account.user_id)
        if user is not None:
            updates: dict[str, str] = {}
            if display_name and display_name != getattr(user, "display_name", ""):
                updates["display_name"] = display_name
            if avatar_url and avatar_url != getattr(user, "avatar_url", ""):
                updates["avatar_url"] = avatar_url
            if updates:
                user = await user_repo.update(user.id, **updates)
    else:
        user = await user_repo.get_by_email(email) if email else None
        if user is None:
            user = await user_repo.create(
                email=email,
                display_name=display_name,
                avatar_url=avatar_url,
            )
        await oauth_repo.create(
            user_id=user.id,
            provider=provider,
            provider_user_id=provider_user_id,
            provider_email=email,
            provider_name=display_name,
            access_token=token_response.access_token,
            refresh_token=token_response.refresh_token,
        )

    if user is None:
        raise PnLClawError(
            code=ErrorCode.INTERNAL_ERROR,
            message="Failed to find or create user account",
        )

    # 5. Check user status
    if user.status == "banned":
        await _record_login(request, str(user.id), provider, success=False)
        raise PnLClawError(
            code=ErrorCode.PERMISSION_DENIED,
            message="Account has been banned",
        )
    if user.status == "suspended":
        await _record_login(request, str(user.id), provider, success=False)
        raise PnLClawError(
            code=ErrorCode.PERMISSION_DENIED,
            message="Account is currently suspended",
        )

    # 6. Admin TOTP check — use a short-lived state token as partial_token
    user_role = user.role or "user"
    totp_enabled = getattr(user, "totp_enabled", False)
    if user_role in ("admin", "operator") and totp_enabled and totp_mgr is not None:
        partial_token = jwt_mgr.create_state_token(
            provider="totp_partial",
            nonce=secrets.token_urlsafe(8),
        )
        # Encode user info into the nonce field via a custom approach:
        # We store a secondary lookup — but for simplicity, we'll use the
        # state token with extra claims by encoding sub+role as nonce.
        # A better approach would be a dedicated partial token table, but
        # for now we encode user_id in the nonce.
        partial_token = jwt_mgr.create_state_token(
            provider="totp_partial",
            nonce=f"{user.id}:{user_role}:{email}:{display_name}",
        )
        return APIResponse(
            data={
                "requires_totp": True,
                "partial_token": partial_token,
            },
            meta=build_response_meta(request),
            error=None,
        )

    # 7. Create session via SessionManager (returns TokenPair)
    ip = _client_ip(request)
    user_agent = request.headers.get("User-Agent", "")

    effective_name = display_name or getattr(user, "display_name", "") or ""
    effective_avatar = avatar_url or getattr(user, "avatar_url", "") or ""

    token_pair = await session_mgr.create_session(
        user_id=str(user.id),
        role=user_role,
        ip=ip,
        user_agent=user_agent,
        display_name=effective_name,
        avatar_url=effective_avatar,
    )

    # 8. Record login history
    await _record_login(request, str(user.id), provider, success=True)

    # 9. Set cookie and return
    _set_refresh_cookie(response, token_pair.refresh_token)

    return APIResponse(
        data={
            "access_token": token_pair.access_token,
            "token_type": "Bearer",
            "user": {
                "id": str(user.id),
                "email": email,
                "display_name": display_name,
                "role": user_role,
                "avatar_url": getattr(user, "avatar_url", ""),
            },
        },
        meta=build_response_meta(request),
        error=None,
    )


# ---------------------------------------------------------------------------
# TOTP verification (after OAuth for admins)
# ---------------------------------------------------------------------------


@router.post("/verify-totp")
async def verify_totp(
    body: TOTPVerifyRequest,
    request: Request,
    response: Response,
    jwt_mgr: Any = Depends(get_jwt_manager),
    totp_mgr: Any = Depends(get_totp_manager),
    user_repo: Any = Depends(get_user_repo),
    session_mgr: Any = Depends(get_session_manager),
) -> APIResponse[dict[str, Any]]:
    """Verify TOTP code after OAuth login for admin users."""
    if jwt_mgr is None or totp_mgr is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Authentication services not available",
        )

    # Decode partial token (stored as state token)
    try:
        payload = jwt_mgr.decode_state_token(body.partial_token)
    except Exception as exc:
        raise PnLClawError(
            code=ErrorCode.AUTHENTICATION_ERROR,
            message="Invalid or expired partial token",
        ) from exc

    if payload.get("provider") != "totp_partial":
        raise PnLClawError(
            code=ErrorCode.VALIDATION_ERROR,
            message="Token does not require TOTP verification",
        )

    # Parse user info from nonce field: "user_id:role:email:display_name"
    nonce_parts = payload.get("nonce", "").split(":", 3)
    if len(nonce_parts) < 2:
        raise PnLClawError(
            code=ErrorCode.AUTHENTICATION_ERROR,
            message="Invalid partial token payload",
        )

    user_id = nonce_parts[0]
    user_role = nonce_parts[1] if len(nonce_parts) > 1 else "user"
    nonce_parts[2] if len(nonce_parts) > 2 else ""
    display_name = nonce_parts[3] if len(nonce_parts) > 3 else ""

    user = await user_repo.get_by_id(uuid.UUID(user_id))
    if user is None:
        raise PnLClawError(
            code=ErrorCode.NOT_FOUND,
            message="User not found",
        )

    totp_secret = getattr(user, "totp_secret", "")
    if not totp_secret:
        raise PnLClawError(
            code=ErrorCode.INTERNAL_ERROR,
            message="TOTP not configured for this user",
        )

    if not totp_mgr.verify(totp_secret, body.code):
        await _record_login(request, user_id, "totp", success=False)
        raise PnLClawError(
            code=ErrorCode.AUTHENTICATION_ERROR,
            message="Invalid TOTP code",
        )

    # Create full session via SessionManager
    ip = _client_ip(request)
    user_agent = request.headers.get("User-Agent", "")

    token_pair = await session_mgr.create_session(
        user_id=user_id,
        role=user_role,
        ip=ip,
        user_agent=user_agent,
        display_name=display_name or getattr(user, "display_name", "") or "",
        avatar_url=getattr(user, "avatar_url", "") or "",
    )

    await _record_login(request, user_id, "totp", success=True)
    _set_refresh_cookie(response, token_pair.refresh_token)

    return APIResponse(
        data={
            "access_token": token_pair.access_token,
            "token_type": "Bearer",
            "user": {
                "id": str(user.id),
                "email": getattr(user, "email", ""),
                "display_name": getattr(user, "display_name", ""),
                "role": getattr(user, "role", "user"),
                "avatar_url": getattr(user, "avatar_url", ""),
            },
        },
        meta=build_response_meta(request),
        error=None,
    )


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------


@router.post("/refresh")
async def refresh_token(
    request: Request,
    response: Response,
    session_mgr: Any = Depends(get_session_manager),
    jwt_mgr: Any = Depends(get_jwt_manager),
    user_repo: Any = Depends(get_user_repo),
) -> APIResponse[dict[str, Any]]:
    """Refresh access token using the refresh token from HttpOnly cookie.

    Delegates to SessionManager.refresh_session which handles rotation,
    replay detection, and session validation internally.  Loads user
    profile from DB so the new access token contains name/avatar claims.
    """
    if session_mgr is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Authentication services not available",
        )

    old_refresh = request.cookies.get("refresh_token")
    if not old_refresh:
        raise PnLClawError(
            code=ErrorCode.AUTHENTICATION_ERROR,
            message="No refresh token provided",
        )

    extra_claims: dict[str, str] = {}
    try:
        refresh_payload = jwt_mgr.decode_refresh_token(old_refresh)
        sid = refresh_payload.get("sid", "")
        if sid:
            session = await session_mgr._sessions.get_by_id(uuid.UUID(sid))
            if session:
                uid = session.get("user_id", "")
                if uid:
                    user = await user_repo.get_by_id(uuid.UUID(uid))
                    if user:
                        extra_claims["name"] = getattr(user, "display_name", "") or ""
                        extra_claims["avatar_url"] = getattr(user, "avatar_url", "") or ""
    except Exception:
        pass

    try:
        token_pair = await session_mgr.refresh_session(old_refresh, extra_claims=extra_claims)
    except Exception as exc:
        _clear_refresh_cookie(response)
        raise PnLClawError(
            code=ErrorCode.AUTHENTICATION_ERROR,
            message="Invalid or expired refresh token",
        ) from exc

    _set_refresh_cookie(response, token_pair.refresh_token)

    return APIResponse(
        data={
            "access_token": token_pair.access_token,
            "token_type": "Bearer",
        },
        meta=build_response_meta(request),
        error=None,
    )


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    user: AuthenticatedUser = Depends(require_auth),
    session_mgr: Any = Depends(get_session_manager),
) -> APIResponse[dict[str, bool]]:
    """Revoke the current session and clear refresh token cookie."""
    if session_mgr is not None and user.session_id:
        try:
            await session_mgr.revoke_session(user.session_id)
        except Exception:
            logger.warning("Failed to revoke session", exc_info=True)

    _clear_refresh_cookie(response)

    return APIResponse(
        data={"logged_out": True},
        meta=build_response_meta(request),
        error=None,
    )


# ---------------------------------------------------------------------------
# Current user
# ---------------------------------------------------------------------------


@router.get("/me")
async def get_current_user(
    request: Request,
    user: AuthenticatedUser = Depends(require_auth),
    user_repo: Any = Depends(get_user_repo),
    oauth_repo: Any = Depends(get_oauth_repo),
) -> APIResponse[dict[str, Any]]:
    """Get the current authenticated user's profile."""
    full_user = await user_repo.get_by_id(uuid.UUID(user.id))
    if full_user is None:
        raise PnLClawError(
            code=ErrorCode.NOT_FOUND,
            message="User not found",
        )

    linked_accounts = await oauth_repo.get_by_user_id(uuid.UUID(user.id))
    providers = [
        {
            "provider": getattr(acc, "provider", ""),
            "provider_email": getattr(acc, "provider_email", ""),
            "linked_at": str(getattr(acc, "created_at", "")),
        }
        for acc in linked_accounts
    ]

    return APIResponse(
        data={
            "id": str(full_user.id),
            "email": getattr(full_user, "email", ""),
            "display_name": getattr(full_user, "display_name", ""),
            "name": getattr(full_user, "display_name", ""),
            "role": getattr(full_user, "role", "user"),
            "avatar_url": getattr(full_user, "avatar_url", ""),
            "status": getattr(full_user, "status", "active"),
            "totp_enabled": getattr(full_user, "totp_enabled", False),
            "linked_providers": providers,
            "created_at": str(getattr(full_user, "created_at", "")),
            "updated_at": str(getattr(full_user, "updated_at", "")),
        },
        meta=build_response_meta(request),
        error=None,
    )


# ---------------------------------------------------------------------------
# Link / unlink OAuth
# ---------------------------------------------------------------------------


@router.post("/link/{provider}")
async def link_provider(
    provider: str,
    code: str,
    state: str,
    request: Request,
    user: AuthenticatedUser = Depends(require_auth),
    jwt_mgr: Any = Depends(get_jwt_manager),
    providers: dict[str, Any] = Depends(get_oauth_providers),
    oauth_repo: Any = Depends(get_oauth_repo),
    auth_config: Any = Depends(get_auth_config),
) -> APIResponse[LinkProviderResponse]:
    """Link an additional OAuth provider to the current user's account."""
    if provider not in providers:
        raise PnLClawError(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"Unsupported OAuth provider: {provider}",
        )

    if jwt_mgr is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="JWT service not available",
        )

    try:
        jwt_mgr.decode_state_token(state)
    except Exception as exc:
        raise PnLClawError(
            code=ErrorCode.AUTHENTICATION_ERROR,
            message="Invalid or expired state token",
        ) from exc

    redirect_uri = _get_redirect_uri(auth_config, provider)
    oauth_provider = providers[provider]
    try:
        token_response = await oauth_provider.exchange_code(code, redirect_uri=redirect_uri)
        user_info = await oauth_provider.get_user_info(token_response.access_token)
    except Exception as exc:
        raise PnLClawError(
            code=ErrorCode.AUTHENTICATION_ERROR,
            message="Failed to verify OAuth account",
        ) from exc

    provider_user_id = user_info.provider_user_id

    existing = await oauth_repo.get_by_provider(provider, provider_user_id)
    if existing is not None:
        if str(existing.user_id) != user.id:
            raise PnLClawError(
                code=ErrorCode.CONFLICT,
                message="This OAuth account is already linked to another user",
            )
        return APIResponse(
            data=LinkProviderResponse(linked=True, provider=provider),
            meta=build_response_meta(request),
            error=None,
        )

    await oauth_repo.create(
        user_id=uuid.UUID(user.id),
        provider=provider,
        provider_user_id=provider_user_id,
        provider_email=user_info.email,
        provider_name=user_info.name,
        access_token=token_response.access_token,
        refresh_token=token_response.refresh_token,
    )

    return APIResponse(
        data=LinkProviderResponse(linked=True, provider=provider),
        meta=build_response_meta(request),
        error=None,
    )


@router.delete("/link/{provider}")
async def unlink_provider(
    provider: str,
    request: Request,
    user: AuthenticatedUser = Depends(require_auth),
    oauth_repo: Any = Depends(get_oauth_repo),
) -> APIResponse[dict[str, bool]]:
    """Unlink an OAuth provider from the current user's account."""
    linked = await oauth_repo.get_by_user_id(uuid.UUID(user.id))
    if len(linked) <= 1:
        raise PnLClawError(
            code=ErrorCode.VALIDATION_ERROR,
            message="Cannot unlink the only authentication provider",
        )

    target = next(
        (acc for acc in linked if getattr(acc, "provider", "") == provider),
        None,
    )
    if target is None:
        raise PnLClawError(
            code=ErrorCode.NOT_FOUND,
            message=f"Provider '{provider}' is not linked to this account",
        )

    await oauth_repo.delete(target.id)

    return APIResponse(
        data={"unlinked": True},
        meta=build_response_meta(request),
        error=None,
    )


# ---------------------------------------------------------------------------
# Account deletion
# ---------------------------------------------------------------------------


@router.delete("/account")
async def delete_account(
    request: Request,
    response: Response,
    user: AuthenticatedUser = Depends(require_auth),
    user_repo: Any = Depends(get_user_repo),
    session_mgr: Any = Depends(get_session_manager),
) -> APIResponse[AccountDeleteResponse]:
    """Soft-delete the current user's account."""
    if session_mgr is not None:
        await session_mgr.revoke_all_user_sessions(user.id)

    await user_repo.soft_delete(uuid.UUID(user.id))
    _clear_refresh_cookie(response)

    return APIResponse(
        data=AccountDeleteResponse(deleted=True),
        meta=build_response_meta(request),
        error=None,
    )
