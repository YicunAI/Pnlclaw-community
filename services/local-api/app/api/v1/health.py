"""Enhanced health check endpoint.

Returns system status with per-component health information
sourced from the ``HealthRegistry`` in ``pnlclaw_core``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from pnlclaw_core.diagnostics.health import HealthRegistry
from pnlclaw_types.common import APIResponse

from app.core.dependencies import build_response_meta, get_health_registry

router = APIRouter(tags=["health"])


def _aggregate_status(components: dict[str, Any]) -> str:
    """Derive overall status from component statuses.

    Rules:
    - Any ``unhealthy`` → ``unhealthy``
    - Any ``degraded`` (but no unhealthy) → ``degraded``
    - Otherwise → ``healthy``
    """
    statuses = {c.get("status", "healthy") for c in components.values()}
    if "unhealthy" in statuses:
        return "unhealthy"
    if "degraded" in statuses:
        return "degraded"
    return "healthy"


@router.get("/health")
async def health_check(
    request: Request,
    registry: HealthRegistry = Depends(get_health_registry),
) -> APIResponse[dict[str, Any]]:
    """Return service health status with per-component breakdown.

    Response includes:
    - ``status``: overall health (healthy / degraded / unhealthy)
    - ``version``: API version string
    - ``components``: dict of component name → {status, latency_ms, detail}
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

    return APIResponse(
        data={
            "status": overall,
            "version": "0.1.0",
            "components": components,
        },
        meta=build_response_meta(request),
        error=None,
    )
