"""Admin 2FA management endpoints -- for admin self-service."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.core.dependencies import (
    AuthenticatedUser,
    build_response_meta,
    get_admin_audit_repo,
    get_totp_manager,
    get_user_repo,
    require_auth,
)
from pnlclaw_types.common import APIResponse
from pnlclaw_types.errors import ErrorCode, PnLClawError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/2fa", tags=["admin-2fa"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class TOTPEnableRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6, description="TOTP verification code")


class TOTPDisableRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6, description="Current TOTP code to confirm")


# ---------------------------------------------------------------------------
# Audit helper
# ---------------------------------------------------------------------------


async def _audit_log(
    admin: AuthenticatedUser,
    action: str,
    details: dict[str, Any] | None = None,
) -> None:
    try:
        audit_repo = get_admin_audit_repo()
        if audit_repo is not None:
            await audit_repo.log(
                admin_user_id=uuid.UUID(admin.id),
                action=action,
                target_user_id=uuid.UUID(admin.id),
                details=details,
            )
    except Exception:
        logger.warning("Failed to write audit log", exc_info=True)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/setup")
async def setup_totp(
    request: Request,
    user: AuthenticatedUser = Depends(require_auth),
    totp_mgr: Any = Depends(get_totp_manager),
    user_repo: Any = Depends(get_user_repo),
) -> APIResponse[dict[str, Any]]:
    """Generate TOTP secret and QR code for 2FA setup.

    Returns the secret key and a QR code data URI that the admin
    can scan with an authenticator app.
    """
    if user.role not in ("admin", "operator"):
        raise PnLClawError(
            code=ErrorCode.PERMISSION_DENIED,
            message="Only admins and operators can configure 2FA",
        )

    if totp_mgr is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="TOTP service not available",
        )

    # Check if already enabled
    full_user = await user_repo.get_by_id(uuid.UUID(user.id))
    if full_user is not None and getattr(full_user, "totp_enabled", False):
        raise PnLClawError(
            code=ErrorCode.CONFLICT,
            message="2FA is already enabled. Disable it first to reconfigure.",
        )

    # Generate new secret
    secret = totp_mgr.generate_secret()
    provisioning_uri = totp_mgr.get_provisioning_uri(
        secret=secret,
        email=user.email,
        issuer="PnLClaw",
    )
    qr_data_uri = f"data:image/png;base64,{totp_mgr.generate_qr_code_base64(provisioning_uri)}"

    # Store pending secret (not yet confirmed)
    await user_repo.update(uuid.UUID(user.id), totp_pending_secret=secret)

    return APIResponse(
        data={
            "secret": secret,
            "provisioning_uri": provisioning_uri,
            "qr_code": qr_data_uri,
        },
        meta=build_response_meta(request),
        error=None,
    )


@router.post("/enable")
async def enable_totp(
    body: TOTPEnableRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_auth),
    totp_mgr: Any = Depends(get_totp_manager),
    user_repo: Any = Depends(get_user_repo),
) -> APIResponse[dict[str, bool]]:
    """Verify TOTP code and enable 2FA.

    The code must match the pending secret generated via /setup.
    """
    if user.role not in ("admin", "operator"):
        raise PnLClawError(
            code=ErrorCode.PERMISSION_DENIED,
            message="Only admins and operators can configure 2FA",
        )

    if totp_mgr is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="TOTP service not available",
        )

    full_user = await user_repo.get_by_id(uuid.UUID(user.id))
    if full_user is None:
        raise PnLClawError(
            code=ErrorCode.NOT_FOUND,
            message="User not found",
        )

    pending_secret = getattr(full_user, "totp_pending_secret", None)
    if not pending_secret:
        raise PnLClawError(
            code=ErrorCode.VALIDATION_ERROR,
            message="No pending 2FA setup. Call /admin/2fa/setup first.",
        )

    # Verify the code
    if not totp_mgr.verify(pending_secret, body.code):
        raise PnLClawError(
            code=ErrorCode.AUTHENTICATION_ERROR,
            message="Invalid TOTP code. Please try again.",
        )

    # Enable 2FA
    await user_repo.update(
        uuid.UUID(user.id),
        totp_secret=pending_secret,
        totp_enabled=True,
        totp_pending_secret=None,
    )

    await _audit_log(user, "enable_2fa")

    return APIResponse(
        data={"enabled": True},
        meta=build_response_meta(request),
        error=None,
    )


@router.post("/disable")
async def disable_totp(
    body: TOTPDisableRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_auth),
    totp_mgr: Any = Depends(get_totp_manager),
    user_repo: Any = Depends(get_user_repo),
) -> APIResponse[dict[str, bool]]:
    """Disable 2FA. Requires the current TOTP code as confirmation."""
    if user.role not in ("admin", "operator"):
        raise PnLClawError(
            code=ErrorCode.PERMISSION_DENIED,
            message="Only admins and operators can configure 2FA",
        )

    if totp_mgr is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="TOTP service not available",
        )

    full_user = await user_repo.get_by_id(uuid.UUID(user.id))
    if full_user is None:
        raise PnLClawError(
            code=ErrorCode.NOT_FOUND,
            message="User not found",
        )

    if not getattr(full_user, "totp_enabled", False):
        raise PnLClawError(
            code=ErrorCode.VALIDATION_ERROR,
            message="2FA is not currently enabled",
        )

    totp_secret = getattr(full_user, "totp_secret", "") or ""
    if not totp_mgr.verify(totp_secret, body.code):
        raise PnLClawError(
            code=ErrorCode.AUTHENTICATION_ERROR,
            message="Invalid TOTP code",
        )

    await user_repo.update(
        uuid.UUID(user.id),
        totp_secret=None,
        totp_enabled=False,
        totp_pending_secret=None,
    )

    await _audit_log(user, "disable_2fa")

    return APIResponse(
        data={"disabled": True},
        meta=build_response_meta(request),
        error=None,
    )
