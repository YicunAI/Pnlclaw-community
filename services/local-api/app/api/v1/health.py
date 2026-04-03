"""Enhanced health check endpoint.

Returns system status with per-component health information
sourced from the ``HealthRegistry`` in ``pnlclaw_core``.

Public endpoint returns only aggregate status; detailed component
information is restricted to localhost / internal requests.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.core.dependencies import build_response_meta, get_health_registry
from pnlclaw_core.diagnostics.health import HealthRegistry
from pnlclaw_types.common import APIResponse

router = APIRouter(tags=["health"])

_IS_PRODUCTION = os.environ.get("PNLCLAW_ENV", "").lower() == "production"


def _aggregate_status(components: dict[str, Any]) -> str:
    """Derive overall status from component statuses."""
    statuses = {c.get("status", "healthy") for c in components.values()}
    if "unhealthy" in statuses:
        return "unhealthy"
    if "degraded" in statuses:
        return "degraded"
    return "healthy"


def _is_internal_request(request: Request) -> bool:
    """Return True if the request originates from localhost / reverse proxy."""
    client = request.client
    if client and client.host in ("127.0.0.1", "::1", "localhost"):
        return True
    forwarded = request.headers.get("x-forwarded-for", "")
    if not forwarded:
        return client is not None and client.host in ("127.0.0.1", "::1")
    return False


@router.get("/health")
async def health_check(
    request: Request,
    registry: HealthRegistry = Depends(get_health_registry),
) -> APIResponse[dict[str, Any]]:
    """Return service health status.

    In production, public requests receive only aggregate status.
    Internal/localhost requests receive full component breakdown.
    """
    results = await registry.run_all()

    components: dict[str, Any] = {}
    for r in results:
        entry: dict[str, Any] = {
            "status": r.status,
            "latency_ms": round(r.latency_ms, 2),
        }
        if r.detail:
            entry["detail"] = r.detail
        components[r.name] = entry

    overall = _aggregate_status(components)

    if _IS_PRODUCTION and not _is_internal_request(request):
        return APIResponse(
            data={"status": overall, "version": "0.1.0"},
            meta=build_response_meta(request),
            error=None,
        )

    return APIResponse(
        data={
            "status": overall,
            "version": "0.1.0",
            "components": components,
        },
        meta=build_response_meta(request),
        error=None,
    )
