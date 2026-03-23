"""Tests for request ID middleware (S3-L08)."""

from __future__ import annotations

import pytest
from app.main import create_app
from httpx import ASGITransport, AsyncClient


def _app():
    return create_app()


@pytest.mark.asyncio
async def test_request_id_generated():
    """Response should include X-Request-ID header."""
    app = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/health")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers
    assert len(resp.headers["X-Request-ID"]) > 0


@pytest.mark.asyncio
async def test_request_id_reused_from_header():
    """If client sends X-Request-ID, it should be echoed back."""
    app = _app()
    transport = ASGITransport(app=app)
    custom_id = "my-custom-request-id-12345"
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(
            "/api/v1/health",
            headers={"X-Request-ID": custom_id},
        )
    assert resp.headers["X-Request-ID"] == custom_id


@pytest.mark.asyncio
async def test_request_id_unique_per_request():
    """Each request should get a unique ID."""
    app = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp1 = await c.get("/api/v1/health")
        resp2 = await c.get("/api/v1/health")
    id1 = resp1.headers["X-Request-ID"]
    id2 = resp2.headers["X-Request-ID"]
    assert id1 != id2


@pytest.mark.asyncio
async def test_request_id_in_response_meta():
    """Request ID should appear in APIResponse meta field."""
    app = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/health")
    assert "X-Request-ID" in resp.headers
    body = resp.json()
    assert body["meta"]["request_id"] == resp.headers["X-Request-ID"]
