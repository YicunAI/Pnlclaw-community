"""Chat session persistence API.

Provides CRUD endpoints for conversation sessions and messages,
enabling the frontend to persist, list, switch, and resume
AI chat conversations across page refreshes.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.dependencies import AuthenticatedUser, get_chat_session_repo, optional_user

router = APIRouter(prefix="/chat", tags=["chat"])

MAX_SESSIONS_PER_USER = 500


class CreateSessionBody(BaseModel):
    strategy_id: str | None = None
    title: str = ""


class UpdateSessionBody(BaseModel):
    title: str


class SaveMessagesBody(BaseModel):
    messages: list[dict[str, Any]] = Field(default_factory=list)


def _require_repo(repo: Any = Depends(get_chat_session_repo)) -> Any:
    if repo is None:
        raise HTTPException(503, "Chat persistence not available")
    return repo


@router.post("/sessions")
async def create_session(
    body: CreateSessionBody,
    repo: Any = Depends(_require_repo),
    user: AuthenticatedUser = Depends(optional_user),
) -> dict[str, Any]:
    existing = await repo.list_sessions(user_id=user.id, limit=1, offset=MAX_SESSIONS_PER_USER)
    if existing:
        raise HTTPException(429, f"Session limit reached ({MAX_SESSIONS_PER_USER})")
    return await repo.create_session(
        strategy_id=body.strategy_id,
        title=body.title,
        user_id=user.id,
    )


@router.get("/sessions")
async def list_sessions(
    strategy_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    repo: Any = Depends(_require_repo),
    user: AuthenticatedUser = Depends(optional_user),
) -> list[dict[str, Any]]:
    return await repo.list_sessions(
        strategy_id=strategy_id,
        limit=limit,
        offset=offset,
        user_id=user.id,
    )


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    repo: Any = Depends(_require_repo),
    user: AuthenticatedUser = Depends(optional_user),
) -> dict[str, Any]:
    row = await repo.get_session(session_id)
    if row is None:
        raise HTTPException(404, "Session not found")
    session_owner = row.get("user_id")
    if user.id != "local":
        if session_owner and session_owner != user.id and session_owner != "local":
            raise HTTPException(403, "Access denied")
        if not session_owner:
            raise HTTPException(403, "Access denied")
    return row


@router.patch("/sessions/{session_id}")
async def update_session(
    session_id: str,
    body: UpdateSessionBody,
    repo: Any = Depends(_require_repo),
    user: AuthenticatedUser = Depends(optional_user),
) -> dict[str, str]:
    existing = await repo.get_session(session_id)
    if existing is None:
        raise HTTPException(404, "Session not found")
    owner = existing.get("user_id")
    if user.id != "local":
        if (owner and owner != user.id and owner != "local") or not owner:
            raise HTTPException(403, "Access denied")
    await repo.update_session_title(session_id, body.title)
    return {"status": "ok"}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    repo: Any = Depends(_require_repo),
    user: AuthenticatedUser = Depends(optional_user),
) -> dict[str, str]:
    existing = await repo.get_session(session_id)
    if existing is None:
        raise HTTPException(404, "Session not found")
    owner = existing.get("user_id")
    if user.id != "local":
        if (owner and owner != user.id and owner != "local") or not owner:
            raise HTTPException(403, "Access denied")
    await repo.delete_session(session_id)
    return {"status": "ok"}


@router.get("/sessions/{session_id}/messages")
async def get_messages(
    session_id: str,
    limit: int = 200,
    offset: int = 0,
    repo: Any = Depends(_require_repo),
    user: AuthenticatedUser = Depends(optional_user),
) -> list[dict[str, Any]]:
    session = await repo.get_session(session_id)
    if session and user.id != "local":
        owner = session.get("user_id")
        if (owner and owner != user.id and owner != "local") or not owner:
            raise HTTPException(403, "Access denied")
    return await repo.get_messages(session_id, limit=limit, offset=offset)


@router.put("/sessions/{session_id}/messages")
async def save_messages(
    session_id: str,
    body: SaveMessagesBody,
    repo: Any = Depends(_require_repo),
    user: AuthenticatedUser = Depends(optional_user),
) -> dict[str, str]:
    """Bulk-save messages for a session (replaces existing messages)."""
    existing = await repo.get_session(session_id)
    if existing is None:
        await repo.create_session(session_id=session_id, user_id=user.id)
    elif user.id != "local":
        owner = existing.get("user_id")
        if (owner and owner != user.id and owner != "local") or not owner:
            raise HTTPException(403, "Access denied")
    await repo.save_messages_bulk(session_id, body.messages)
    return {"status": "ok"}
