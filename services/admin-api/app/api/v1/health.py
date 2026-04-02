"""Health check endpoint with PostgreSQL connection verification."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.core.dependencies import build_response_meta, get_postgres_manager
from pnlclaw_types.common import APIResponse

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(
    request: Request,
    pg: Any = Depends(get_postgres_manager),
) -> APIResponse[dict[str, Any]]:
    """Return service health status including PostgreSQL connectivity.

    Response includes:
    - ``status``: overall health (healthy / unhealthy)
    - ``version``: API version string
    - ``components.postgres``: database connection status and latency
    """
    components: dict[str, Any] = {}

    # Check PostgreSQL
    pg_status = "unhealthy"
    pg_latency_ms = 0.0
    if pg is not None:
        start = time.monotonic()
        try:
            ok = await pg.health_check()
            pg_latency_ms = (time.monotonic() - start) * 1000
            pg_status = "healthy" if ok else "unhealthy"
        except Exception:
            pg_latency_ms = (time.monotonic() - start) * 1000
            pg_status = "unhealthy"

    components["postgres"] = {
        "status": pg_status,
        "latency_ms": round(pg_latency_ms, 2),
    }

    overall = "healthy" if pg_status == "healthy" else "unhealthy"

    return APIResponse(
        data={
            "status": overall,
            "version": "0.1.0",
            "service": "admin-api",
            "components": components,
        },
        meta=build_response_meta(request),
        error=None,
    )
