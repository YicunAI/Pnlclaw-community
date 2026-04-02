"""Invitation management endpoints -- admin only."""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.core.dependencies import (
    AuthenticatedUser,
    build_response_meta,
    get_admin_audit_repo,
    get_postgres_manager,
    require_admin,
)
from pnlclaw_types.common import APIResponse, Pagination
from pnlclaw_types.errors import ErrorCode, PnLClawError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/invitations", tags=["admin-invitations"])

_VALID_ROLES = ("user", "operator", "admin")


class InvitationCreateRequest(BaseModel):
    role: str = Field("user", description="Role to assign on registration")
    max_uses: int = Field(1, ge=1, le=1000, description="Max number of uses")
    expires_in_hours: int = Field(
        168,
        ge=1,
        le=8760,
        description="Hours until expiration (default 7 days)",
    )
    note: str = Field("", max_length=500)


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
                details=details,
            )
    except Exception:
        logger.warning("Failed to write audit log", exc_info=True)


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert a SQLAlchemy row mapping to a JSON-safe dict."""
    d = dict(row)
    for k, v in d.items():
        if isinstance(v, uuid.UUID):
            d[k] = str(v)
        elif isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


def _safe_uuid(value: str, field_name: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise PnLClawError(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"Invalid UUID format for {field_name}: {value}",
        )


@router.get("")
async def list_invitations(
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    pg: Any = Depends(get_postgres_manager),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> APIResponse[dict[str, Any]]:
    """List all invitations with pagination."""
    if pg is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Database not available",
        )

    async with pg.session() as session:
        result = await session.execute(
            text(
                "SELECT id, code, role, max_uses, used_count, note, "
                "created_by, created_at, expires_at "
                "FROM invitations ORDER BY created_at DESC "
                "OFFSET :off LIMIT :lim"
            ),
            {"off": offset, "lim": limit},
        )
        rows = result.mappings().all()

        count_result = await session.execute(text("SELECT COUNT(*) as total FROM invitations"))
        total = (count_result.mappings().first() or {}).get("total", 0)

    invitations = [_row_to_dict(r) for r in rows]
    pagination = Pagination(offset=offset, limit=limit, total=total)

    return APIResponse(
        data={"invitations": invitations, "total": total},
        meta=build_response_meta(request, pagination=pagination),
        error=None,
    )


@router.post("")
async def create_invitation(
    body: InvitationCreateRequest,
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    pg: Any = Depends(get_postgres_manager),
) -> APIResponse[dict[str, Any]]:
    """Create a new invitation code."""
    if pg is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Database not available",
        )

    effective_role = body.role
    if effective_role == "moderator":
        effective_role = "operator"
    if effective_role not in _VALID_ROLES:
        raise PnLClawError(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"Invalid role: {body.role}. Must be one of {_VALID_ROLES}",
        )

    if effective_role in ("admin", "operator") and admin.role != "admin":
        raise PnLClawError(
            code=ErrorCode.PERMISSION_DENIED,
            message="Only admins can create invitations for privileged roles",
        )

    code = secrets.token_urlsafe(12)[:16]
    inv_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=body.expires_in_hours)

    async with pg.session() as session:
        result = await session.execute(
            text(
                "INSERT INTO invitations (id, code, role, max_uses, used_count, note, created_by, created_at, expires_at) "
                "VALUES (:id, :code, :role, :max_uses, 0, :note, :created_by, :created_at, :expires_at) "
                "RETURNING id, code, role, max_uses, used_count, note, created_by, created_at, expires_at"
            ),
            {
                "id": inv_id,
                "code": code,
                "role": effective_role,
                "max_uses": body.max_uses,
                "note": body.note,
                "created_by": uuid.UUID(admin.id),
                "created_at": now,
                "expires_at": expires_at,
            },
        )
        row = result.mappings().first()
        await session.commit()

    invitation = _row_to_dict(row) if row else {}
    await _audit_log(admin, "create_invitation", details={"code": code, "role": effective_role})

    return APIResponse(
        data=invitation,
        meta=build_response_meta(request),
        error=None,
    )


@router.delete("/{invitation_id}")
async def delete_invitation(
    invitation_id: str,
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    pg: Any = Depends(get_postgres_manager),
) -> APIResponse[dict[str, bool]]:
    """Delete an invitation."""
    if pg is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Database not available",
        )

    uid = _safe_uuid(invitation_id, "invitation_id")

    async with pg.session() as session:
        await session.execute(
            text("DELETE FROM invitations WHERE id = :id"),
            {"id": uid},
        )
        await session.commit()

    await _audit_log(admin, "delete_invitation", details={"invitation_id": invitation_id})

    return APIResponse(
        data={"deleted": True},
        meta=build_response_meta(request),
        error=None,
    )
