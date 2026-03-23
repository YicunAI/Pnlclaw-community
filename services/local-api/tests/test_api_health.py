"""Tests for the enhanced health check endpoint (S3-L01)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from pnlclaw_core.diagnostics.health import HealthCheckResult, HealthRegistry

from app.core.dependencies import get_health_registry
from app.main import create_app


def _make_app(registry: HealthRegistry | None = None):
    app = create_app()
    if registry is not None:
        app.dependency_overrides[get_health_registry] = lambda: registry
    return app


@pytest.mark.asyncio
async def test_health_no_components():
    app = _make_app(HealthRegistry())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["status"] == "healthy"
    assert body["data"]["version"] == "0.1.0"
    assert body["data"]["components"] == {}
    assert body["error"] is None


@pytest.mark.asyncio
async def test_health_all_healthy():
    registry = HealthRegistry()

    async def _ok():
        return HealthCheckResult(name="db", status="healthy", latency_ms=0)

    registry.register_check("db", _ok)
    app = _make_app(registry)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
    body = resp.json()
    assert body["data"]["status"] == "healthy"
    assert "db" in body["data"]["components"]
    assert body["data"]["components"]["db"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_degraded():
    registry = HealthRegistry()

    async def _ok():
        return HealthCheckResult(name="ws", status="healthy", latency_ms=0)

    async def _degraded():
        return HealthCheckResult(name="llm", status="degraded", latency_ms=0)

    registry.register_check("ws", _ok)
    registry.register_check("llm", _degraded)
    app = _make_app(registry)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
    body = resp.json()
    assert body["data"]["status"] == "degraded"


@pytest.mark.asyncio
async def test_health_unhealthy():
    registry = HealthRegistry()

    async def _bad():
        raise RuntimeError("connection lost")

    registry.register_check("exchange_ws", _bad)
    app = _make_app(registry)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
    body = resp.json()
    assert body["data"]["status"] == "unhealthy"
    assert body["data"]["components"]["exchange_ws"]["status"] == "unhealthy"
