"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    """Return service health status.

    Returns 200 with component-level health once diagnostics are wired.
    """
    return {
        "status": "ok",
        "version": "0.1.0",
        "components": {},
    }
