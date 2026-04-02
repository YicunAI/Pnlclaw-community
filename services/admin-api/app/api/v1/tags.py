"""Tag management endpoints -- admin only."""

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
    get_user_tag_repo,
    require_admin,
)
from pnlclaw_types.common import APIResponse
from pnlclaw_types.errors import ErrorCode, PnLClawError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/tags", tags=["admin-tags"])


def _tag_to_dict(tag: Any) -> dict[str, Any]:
    return {
        "id": str(tag.id),
        "name": tag.name,
        "color": tag.color,
        "description": getattr(tag, "description", None),
        "created_at": tag.created_at.isoformat() if tag.created_at else None,
        "user_count": getattr(tag, "usage_count", 0),
    }


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class TagCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color: str = Field("#6366f1", max_length=7, description="Hex color code")
    description: str = Field("", max_length=500)


class TagUpdateRequest(BaseModel):
    name: str | None = None
    color: str | None = None
    description: str | None = None


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
                details=details,
            )
    except Exception:
        logger.warning("Failed to write audit log", exc_info=True)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_tags(
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    user_tag_repo: Any = Depends(get_user_tag_repo),
) -> APIResponse[dict[str, Any]]:
    """List all tags with usage counts."""
    if user_tag_repo is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Tag management not available",
        )

    tags = await user_tag_repo.list_tags()

    return APIResponse(
        data={"tags": [_tag_to_dict(t) for t in tags], "total": len(tags)},
        meta=build_response_meta(request),
        error=None,
    )


@router.post("")
async def create_tag(
    body: TagCreateRequest,
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    user_tag_repo: Any = Depends(get_user_tag_repo),
) -> APIResponse[dict[str, Any]]:
    """Create a new tag."""
    if user_tag_repo is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Tag management not available",
        )

    create_kwargs: dict[str, Any] = {"name": body.name, "color": body.color}
    if body.description:
        create_kwargs["description"] = body.description
    tag = await user_tag_repo.create_tag(**create_kwargs)

    await _audit_log(admin, "create_tag", details={"name": body.name})

    return APIResponse(
        data=_tag_to_dict(tag),
        meta=build_response_meta(request),
        error=None,
    )


@router.patch("/{tag_id}")
async def update_tag(
    tag_id: str,
    body: TagUpdateRequest,
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    user_tag_repo: Any = Depends(get_user_tag_repo),
) -> APIResponse[dict[str, Any]]:
    """Update an existing tag."""
    if user_tag_repo is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Tag management not available",
        )

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise PnLClawError(
            code=ErrorCode.VALIDATION_ERROR,
            message="No fields to update",
        )
    if not any(k in updates for k in ("name", "color", "description")):
        raise PnLClawError(
            code=ErrorCode.VALIDATION_ERROR,
            message="No fields to update",
        )

    try:
        tag = await user_tag_repo.update_tag(
            uuid.UUID(tag_id),
            name=updates.get("name"),
            color=updates.get("color"),
            description=updates.get("description"),
        )
    except ValueError:
        raise PnLClawError(
            code=ErrorCode.NOT_FOUND,
            message=f"Tag '{tag_id}' not found",
        ) from None

    await _audit_log(admin, "update_tag", details={"tag_id": tag_id, **updates})

    return APIResponse(
        data=_tag_to_dict(tag),
        meta=build_response_meta(request),
        error=None,
    )


@router.delete("/{tag_id}")
async def delete_tag(
    tag_id: str,
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    user_tag_repo: Any = Depends(get_user_tag_repo),
) -> APIResponse[dict[str, bool]]:
    """Delete a tag and remove all user assignments."""
    if user_tag_repo is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Tag management not available",
        )

    await user_tag_repo.delete_tag(uuid.UUID(tag_id))
    await _audit_log(admin, "delete_tag", details={"tag_id": tag_id})

    return APIResponse(
        data={"deleted": True},
        meta=build_response_meta(request),
        error=None,
    )
