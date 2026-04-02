"""User management endpoints -- admin only."""

from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.dependencies import (
    AuthenticatedUser,
    build_response_meta,
    get_activity_repo,
    get_admin_audit_repo,
    get_admin_note_repo,
    get_login_history_repo,
    get_session_manager,
    get_session_repo,
    get_user_repo,
    get_user_tag_repo,
    require_admin,
)
from pnlclaw_types.common import APIResponse, Pagination
from pnlclaw_types.errors import ErrorCode, PnLClawError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/users", tags=["admin-users"])
sessions_router = APIRouter(prefix="/admin/sessions", tags=["admin-sessions"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class UserUpdateRequest(BaseModel):
    display_name: str | None = None
    email: str | None = None
    role: str | None = None
    status: str | None = None


class BanRequest(BaseModel):
    reason: str = Field("", description="Reason for banning")


class SuspendRequest(BaseModel):
    reason: str = Field("", description="Reason for suspension")
    until: str | None = Field(None, description="ISO datetime to suspend until")


class TagAssignRequest(BaseModel):
    tag_id: str


class NoteCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class BulkActionRequest(BaseModel):
    action: Literal["ban", "suspend", "activate", "delete"]
    user_ids: list[str] = Field(..., min_length=1, max_length=100)
    reason: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user_to_dict(user: Any, *, include_tags: bool = False) -> dict[str, Any]:
    """Serialize an ORM User to a JSON-safe dict."""
    d: dict[str, Any] = {
        "id": str(user.id),
        "email": getattr(user, "email", None),
        "name": getattr(user, "display_name", None),
        "display_name": getattr(user, "display_name", None),
        "role": getattr(user, "role", "user"),
        "status": getattr(user, "status", "active"),
        "avatar_url": getattr(user, "avatar_url", None),
        "country": getattr(user, "last_country", None),
        "city": getattr(user, "last_city", None),
        "last_login": str(getattr(user, "last_login_at", "")) or None,
        "created_at": str(getattr(user, "created_at", "")),
        "updated_at": str(getattr(user, "updated_at", "")),
    }
    oauth_accounts = getattr(user, "oauth_accounts", None)
    if oauth_accounts is not None:
        d["oauth_accounts"] = [
            {
                "id": str(a.id),
                "provider": a.provider,
                "email": getattr(a, "provider_email", None),
            }
            for a in oauth_accounts
        ]
    else:
        d["oauth_accounts"] = []
    if include_tags:
        tags = getattr(user, "tag_assignments", None)
        if tags is not None:
            d["tags"] = [
                {
                    "id": str(ta.tag.id) if getattr(ta, "tag", None) else str(ta.tag_id),
                    "name": ta.tag.name if getattr(ta, "tag", None) else "",
                    "color": ta.tag.color if getattr(ta, "tag", None) else "#6366f1",
                }
                for ta in tags
            ]
        else:
            d["tags"] = []
    return d


def _activity_to_dict(a: Any) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "action": getattr(a, "event_type", ""),
        "details": str(getattr(a, "details", "") or ""),
        "ip_address": getattr(a, "ip_address", None),
        "created_at": str(getattr(a, "created_at", "")),
    }


def _login_history_to_dict(e: Any) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "provider": getattr(e, "provider", ""),
        "ip_address": getattr(e, "ip_address", None),
        "country": getattr(e, "country", None),
        "city": getattr(e, "city", None),
        "device": getattr(e, "device_type", None),
        "os": getattr(e, "os", None),
        "browser": getattr(e, "browser", None),
        "success": getattr(e, "success", True),
        "failure_reason": getattr(e, "failure_reason", None),
        "created_at": str(getattr(e, "created_at", "")),
    }


def _session_to_dict(s: Any) -> dict[str, Any]:
    ua = getattr(s, "user_agent", "") or ""
    browser = ""
    os_name = ""
    if "Chrome" in ua:
        browser = "Chrome"
    elif "Firefox" in ua:
        browser = "Firefox"
    elif "Safari" in ua:
        browser = "Safari"
    elif "Edge" in ua:
        browser = "Edge"
    if "Windows" in ua:
        os_name = "Windows"
    elif "Mac" in ua:
        os_name = "macOS"
    elif "Linux" in ua:
        os_name = "Linux"
    elif "Android" in ua:
        os_name = "Android"
    elif "iPhone" in ua or "iPad" in ua:
        os_name = "iOS"
    return {
        "id": str(s.id),
        "ip_address": getattr(s, "ip_address", None),
        "user_agent": ua,
        "browser": browser or None,
        "os": os_name or None,
        "country": None,
        "city": None,
        "last_active": str(getattr(s, "created_at", "")),
        "is_current": False,
        "created_at": str(getattr(s, "created_at", "")),
        "expires_at": str(getattr(s, "expires_at", "")),
    }


def _note_to_dict(n: Any, admin_name: str | None = None) -> dict[str, Any]:
    return {
        "id": str(n.id),
        "user_id": str(getattr(n, "user_id", "")),
        "admin_id": str(getattr(n, "admin_id", "")),
        "admin_name": admin_name or str(getattr(n, "admin_id", "")),
        "content": getattr(n, "content", ""),
        "created_at": str(getattr(n, "created_at", "")),
        "updated_at": str(getattr(n, "updated_at", "")),
    }


def _safe_uuid(value: str, field_name: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise PnLClawError(
            code=ErrorCode.VALIDATION_ERROR,
            message=f"Invalid UUID format for {field_name}: {value}",
        )


async def _audit_log(
    admin: AuthenticatedUser,
    action: str,
    target_user_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Record an admin action in the audit log."""
    try:
        audit_repo = get_admin_audit_repo()
        if audit_repo is not None:
            await audit_repo.log(
                admin_user_id=uuid.UUID(admin.id),
                action=action,
                target_user_id=uuid.UUID(target_user_id) if target_user_id else None,
                details=details,
            )
    except Exception:
        logger.warning("Failed to write audit log", exc_info=True)


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------


@router.get("")
async def list_users(
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    user_repo: Any = Depends(get_user_repo),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: str | None = Query(None),
    role: str | None = Query(None),
    search: str | None = Query(None, description="Search by email or display name"),
    tag: str | None = Query(None, description="Filter by tag name"),
    sort_by: str = Query("created_at", pattern="^(created_at|email|display_name|role|status)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
) -> APIResponse[dict[str, Any]]:
    """List users with pagination, filtering, and search."""
    users, total = await user_repo.list_users(
        search=search,
        status=status,
        role=role,
        tag=tag,
        sort_by=sort_by,
        sort_order=sort_order,
        offset=offset,
        limit=limit,
    )

    pagination = Pagination(offset=offset, limit=limit, total=total)

    return APIResponse(
        data={
            "users": [_user_to_dict(u) for u in users],
            "total": total,
        },
        meta=build_response_meta(request, pagination=pagination),
        error=None,
    )


@router.get("/export")
async def export_users(
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    user_repo: Any = Depends(get_user_repo),
    format: Literal["csv", "json"] = Query("csv"),
    status: str | None = Query(None),
    role: str | None = Query(None),
) -> StreamingResponse:
    """Export users as CSV or JSON (up to 10000)."""
    await _audit_log(admin, "export_users", details={"format": format})

    users, _total = await user_repo.list_users(
        status=status,
        role=role,
        sort_by="created_at",
        sort_order="desc",
        offset=0,
        limit=10000,
    )

    serialized = [_user_to_dict(u) for u in users]

    if format == "json":
        content = json.dumps(serialized, indent=2, default=str)
        return StreamingResponse(
            iter([content]),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=users_export.json"},
        )

    output = io.StringIO()
    if serialized:
        fieldnames = list(serialized[0].keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for u in serialized:
            writer.writerow({k: str(v) for k, v in u.items()})

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=users_export.csv"},
    )


@router.get("/{user_id}")
async def get_user(
    user_id: str,
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    user_repo: Any = Depends(get_user_repo),
) -> APIResponse[dict[str, Any]]:
    """Get detailed user information."""
    user = await user_repo.get_by_id(_safe_uuid(user_id, "user_id"))
    if user is None:
        raise PnLClawError(
            code=ErrorCode.NOT_FOUND,
            message=f"User '{user_id}' not found",
        )

    return APIResponse(
        data=_user_to_dict(user, include_tags=True),
        meta=build_response_meta(request),
        error=None,
    )


@router.patch("/{user_id}")
async def update_user(
    user_id: str,
    body: UserUpdateRequest,
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    user_repo: Any = Depends(get_user_repo),
) -> APIResponse[dict[str, Any]]:
    """Update user fields."""
    user = await user_repo.get_by_id(_safe_uuid(user_id))
    if user is None:
        raise PnLClawError(
            code=ErrorCode.NOT_FOUND,
            message=f"User '{user_id}' not found",
        )

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise PnLClawError(
            code=ErrorCode.VALIDATION_ERROR,
            message="No fields to update",
        )

    # Prevent privilege escalation: only admins can change roles,
    # and no one can set role to admin via this endpoint
    if "role" in updates:
        if admin.role != "admin":
            raise PnLClawError(
                code=ErrorCode.PERMISSION_DENIED,
                message="Only admins can change user roles",
            )
        if updates["role"] == "admin" and user_id != admin.id:
            raise PnLClawError(
                code=ErrorCode.PERMISSION_DENIED,
                message="Cannot promote users to admin via this endpoint",
            )

    updated = await user_repo.update(_safe_uuid(user_id), **updates)
    await _audit_log(admin, "update_user", target_user_id=user_id, details=updates)

    return APIResponse(
        data=_user_to_dict(updated),
        meta=build_response_meta(request),
        error=None,
    )


# ---------------------------------------------------------------------------
# Status changes
# ---------------------------------------------------------------------------


@router.post("/{user_id}/ban")
async def ban_user(
    user_id: str,
    body: BanRequest,
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    user_repo: Any = Depends(get_user_repo),
    session_mgr: Any = Depends(get_session_manager),
) -> APIResponse[dict[str, Any]]:
    """Ban a user and revoke all their sessions."""
    user = await user_repo.get_by_id(_safe_uuid(user_id))
    if user is None:
        raise PnLClawError(
            code=ErrorCode.NOT_FOUND,
            message=f"User '{user_id}' not found",
        )

    if user.role in ("admin", "operator"):
        raise PnLClawError(
            code=ErrorCode.PERMISSION_DENIED,
            message="Cannot ban admin or operator users",
        )

    updated = await user_repo.update(_safe_uuid(user_id), **{
        "status": "banned",
        "ban_reason": body.reason,
    })

    if session_mgr is not None:
        await session_mgr.revoke_all_user_sessions(user_id)

    await _audit_log(admin, "ban_user", target_user_id=user_id, details={"reason": body.reason})

    return APIResponse(
        data=_user_to_dict(updated),
        meta=build_response_meta(request),
        error=None,
    )


@router.post("/{user_id}/suspend")
async def suspend_user(
    user_id: str,
    body: SuspendRequest,
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    user_repo: Any = Depends(get_user_repo),
    session_mgr: Any = Depends(get_session_manager),
) -> APIResponse[dict[str, Any]]:
    """Suspend a user temporarily."""
    user = await user_repo.get_by_id(_safe_uuid(user_id))
    if user is None:
        raise PnLClawError(
            code=ErrorCode.NOT_FOUND,
            message=f"User '{user_id}' not found",
        )

    if user.role in ("admin", "operator"):
        raise PnLClawError(
            code=ErrorCode.PERMISSION_DENIED,
            message="Cannot suspend admin or operator users",
        )

    update_fields: dict[str, Any] = {"status": "suspended"}
    if body.reason:
        update_fields["ban_reason"] = body.reason
    if body.until:
        try:
            until_dt = datetime.fromisoformat(body.until)
            update_fields["suspended_until"] = until_dt
        except (ValueError, TypeError):
            raise PnLClawError(
                code=ErrorCode.VALIDATION_ERROR,
                message=f"Invalid ISO datetime for 'until': {body.until}",
            )

    updated = await user_repo.update(_safe_uuid(user_id), **update_fields)

    if session_mgr is not None:
        await session_mgr.revoke_all_user_sessions(user_id)

    await _audit_log(
        admin, "suspend_user", target_user_id=user_id,
        details={"reason": body.reason, "until": body.until},
    )

    return APIResponse(
        data=_user_to_dict(updated),
        meta=build_response_meta(request),
        error=None,
    )


@router.post("/{user_id}/activate")
async def activate_user(
    user_id: str,
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    user_repo: Any = Depends(get_user_repo),
) -> APIResponse[dict[str, Any]]:
    """Activate (unban/unsuspend) a user."""
    user = await user_repo.get_by_id(_safe_uuid(user_id))
    if user is None:
        raise PnLClawError(
            code=ErrorCode.NOT_FOUND,
            message=f"User '{user_id}' not found",
        )

    updated = await user_repo.update(_safe_uuid(user_id), **{
        "status": "active",
        "ban_reason": None,
    })

    await _audit_log(admin, "activate_user", target_user_id=user_id)

    return APIResponse(
        data=_user_to_dict(updated),
        meta=build_response_meta(request),
        error=None,
    )


# ---------------------------------------------------------------------------
# Activity and login history
# ---------------------------------------------------------------------------


@router.get("/{user_id}/activity")
async def get_user_activity(
    user_id: str,
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    activity_repo: Any = Depends(get_activity_repo),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> APIResponse[dict[str, Any]]:
    """Get activity log for a specific user."""
    if activity_repo is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Activity tracking not available",
        )

    uid = _safe_uuid(user_id, "user_id")
    activities = await activity_repo.query(
        user_id=uid,
        offset=offset,
        limit=limit,
    )

    return APIResponse(
        data={"activities": [_activity_to_dict(a) for a in activities], "total": len(activities)},
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/{user_id}/login-history")
async def get_login_history(
    user_id: str,
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    login_history_repo: Any = Depends(get_login_history_repo),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> APIResponse[dict[str, Any]]:
    """Get login history for a specific user."""
    if login_history_repo is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Login history not available",
        )

    uid = _safe_uuid(user_id, "user_id")
    entries = await login_history_repo.get_for_user(
        user_id=uid,
        offset=offset,
        limit=limit,
    )

    return APIResponse(
        data={"entries": [_login_history_to_dict(e) for e in entries], "total": len(entries)},
        meta=build_response_meta(request),
        error=None,
    )


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@router.get("/{user_id}/sessions")
async def get_user_sessions(
    user_id: str,
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    session_repo: Any = Depends(get_session_repo),
) -> APIResponse[dict[str, Any]]:
    """Get active sessions for a user."""
    if session_repo is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Session management not available",
        )

    uid = _safe_uuid(user_id, "user_id")
    sessions = await session_repo.get_active_for_user(uid)

    return APIResponse(
        data={"sessions": [_session_to_dict(s) for s in sessions], "total": len(sessions)},
        meta=build_response_meta(request),
        error=None,
    )


@router.delete("/{user_id}/sessions")
async def revoke_user_sessions(
    user_id: str,
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    session_mgr: Any = Depends(get_session_manager),
) -> APIResponse[dict[str, bool]]:
    """Revoke all sessions for a user."""
    if session_mgr is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Session management not available",
        )

    await session_mgr.revoke_all_user_sessions(user_id)
    await _audit_log(admin, "revoke_all_sessions", target_user_id=user_id)

    return APIResponse(
        data={"revoked": True},
        meta=build_response_meta(request),
        error=None,
    )


@sessions_router.delete("/{session_id}")
async def revoke_single_session(
    session_id: str,
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    session_repo: Any = Depends(get_session_repo),
) -> APIResponse[dict[str, bool]]:
    """Revoke a single session by ID."""
    if session_repo is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Session management not available",
        )

    sid = _safe_uuid(session_id, "session_id")
    session = await session_repo.get_by_id(sid) if hasattr(session_repo, "get_by_id") else None
    if session is not None:
        await session_repo.revoke(sid) if hasattr(session_repo, "revoke") else None
    elif hasattr(session_repo, "revoke"):
        await session_repo.revoke(sid)

    await _audit_log(admin, "revoke_session", details={"session_id": session_id})

    return APIResponse(
        data={"revoked": True},
        meta=build_response_meta(request),
        error=None,
    )


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


@router.post("/{user_id}/tags")
async def assign_tag(
    user_id: str,
    body: TagAssignRequest,
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    user_tag_repo: Any = Depends(get_user_tag_repo),
    user_repo: Any = Depends(get_user_repo),
) -> APIResponse[dict[str, Any]]:
    """Assign a tag to a user."""
    user = await user_repo.get_by_id(_safe_uuid(user_id))
    if user is None:
        raise PnLClawError(
            code=ErrorCode.NOT_FOUND,
            message=f"User '{user_id}' not found",
        )

    if user_tag_repo is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Tag management not available",
        )

    await user_tag_repo.assign_tag(
        user_id=_safe_uuid(user_id),
        tag_id=_safe_uuid(body.tag_id, "tag_id"),
        assigned_by=uuid.UUID(admin.id),
    )
    await _audit_log(
        admin, "assign_tag", target_user_id=user_id,
        details={"tag_id": body.tag_id},
    )

    return APIResponse(
        data={"assigned": True},
        meta=build_response_meta(request),
        error=None,
    )


@router.delete("/{user_id}/tags/{tag_id}")
async def remove_tag(
    user_id: str,
    tag_id: str,
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    user_tag_repo: Any = Depends(get_user_tag_repo),
) -> APIResponse[dict[str, bool]]:
    """Remove a tag from a user."""
    if user_tag_repo is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Tag management not available",
        )

    await user_tag_repo.remove_tag(
        user_id=_safe_uuid(user_id),
        tag_id=_safe_uuid(tag_id, "tag_id"),
    )
    await _audit_log(
        admin, "remove_tag", target_user_id=user_id,
        details={"tag_id": tag_id},
    )

    return APIResponse(
        data={"removed": True},
        meta=build_response_meta(request),
        error=None,
    )


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------


@router.post("/{user_id}/notes")
async def add_note(
    user_id: str,
    body: NoteCreateRequest,
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    admin_note_repo: Any = Depends(get_admin_note_repo),
    user_repo: Any = Depends(get_user_repo),
) -> APIResponse[dict[str, Any]]:
    """Add an admin note to a user."""
    uid = _safe_uuid(user_id, "user_id")
    user = await user_repo.get_by_id(uid)
    if user is None:
        raise PnLClawError(
            code=ErrorCode.NOT_FOUND,
            message=f"User '{user_id}' not found",
        )

    if admin_note_repo is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Notes not available",
        )

    note = await admin_note_repo.create(
        user_id=uid,
        admin_id=uuid.UUID(admin.id),
        content=body.content,
    )

    admin_name = getattr(admin, "display_name", None) or getattr(admin, "email", None) or admin.id
    return APIResponse(
        data=_note_to_dict(note, admin_name=admin_name),
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/{user_id}/notes")
async def list_notes(
    user_id: str,
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    admin_note_repo: Any = Depends(get_admin_note_repo),
    user_repo: Any = Depends(get_user_repo),
) -> APIResponse[dict[str, Any]]:
    """List admin notes for a user."""
    if admin_note_repo is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Notes not available",
        )

    uid = _safe_uuid(user_id, "user_id")
    notes = await admin_note_repo.list_for_user(uid)

    admin_cache: dict[str, str] = {}
    result = []
    for n in notes:
        aid = str(getattr(n, "admin_id", ""))
        if aid and aid not in admin_cache:
            admin_user = await user_repo.get_by_id(uuid.UUID(aid)) if aid else None
            if admin_user:
                admin_cache[aid] = getattr(admin_user, "display_name", None) or getattr(admin_user, "email", "") or aid
            else:
                admin_cache[aid] = aid
        result.append(_note_to_dict(n, admin_name=admin_cache.get(aid, aid)))

    return APIResponse(
        data={"notes": result, "total": len(result)},
        meta=build_response_meta(request),
        error=None,
    )


@router.delete("/{user_id}/notes/{note_id}")
async def delete_note(
    user_id: str,
    note_id: str,
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    admin_note_repo: Any = Depends(get_admin_note_repo),
) -> APIResponse[dict[str, bool]]:
    """Delete an admin note (verifies it belongs to the given user)."""
    if admin_note_repo is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Notes not available",
        )

    uid = _safe_uuid(user_id, "user_id")
    nid = _safe_uuid(note_id, "note_id")

    note = await admin_note_repo.get_by_id(nid) if hasattr(admin_note_repo, "get_by_id") else None
    if note is not None and str(getattr(note, "user_id", "")) != str(uid):
        raise PnLClawError(
            code=ErrorCode.PERMISSION_DENIED,
            message="Note does not belong to this user",
        )

    await admin_note_repo.delete(nid)

    return APIResponse(
        data={"deleted": True},
        meta=build_response_meta(request),
        error=None,
    )


# ---------------------------------------------------------------------------
# Bulk operations
# ---------------------------------------------------------------------------


@router.post("/bulk-action")
async def bulk_action(
    body: BulkActionRequest,
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin),
    user_repo: Any = Depends(get_user_repo),
    session_mgr: Any = Depends(get_session_manager),
) -> APIResponse[dict[str, Any]]:
    """Perform bulk operations on multiple users."""
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for uid in body.user_ids:
        try:
            uid_uuid = uuid.UUID(uid)
            user = await user_repo.get_by_id(uid_uuid)
            if user is None:
                errors.append({"user_id": uid, "error": "Not found"})
                continue

            if user.role in ("admin", "operator") and body.action in ("ban", "suspend", "delete"):
                errors.append({"user_id": uid, "error": "Cannot modify admin/operator"})
                continue

            if body.action == "ban":
                await user_repo.update(uid_uuid, **{
                    "status": "banned",
                    "ban_reason": body.reason,
                })
                if session_mgr is not None:
                    await session_mgr.revoke_all_user_sessions(uid)

            elif body.action == "suspend":
                await user_repo.update(uid_uuid, status="suspended")
                if session_mgr is not None:
                    await session_mgr.revoke_all_user_sessions(uid)

            elif body.action == "activate":
                await user_repo.update(uid_uuid, status="active", ban_reason=None)

            elif body.action == "delete":
                await user_repo.soft_delete(uid_uuid)
                if session_mgr is not None:
                    await session_mgr.revoke_all_user_sessions(uid)

            results.append({"user_id": uid, "status": "ok"})

        except Exception as exc:
            logger.warning("Bulk action failed for user %s: %s", uid, exc)
            errors.append({"user_id": uid, "error": str(exc)})

    await _audit_log(
        admin, f"bulk_{body.action}",
        details={
            "user_ids": body.user_ids,
            "reason": body.reason,
            "success_count": len(results),
            "error_count": len(errors),
        },
    )

    return APIResponse(
        data={
            "action": body.action,
            "processed": len(results),
            "errors": errors,
            "results": results,
        },
        meta=build_response_meta(request),
        error=None,
    )
