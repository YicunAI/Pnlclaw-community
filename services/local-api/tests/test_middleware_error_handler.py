"""Tests for error handler middleware (S3-L07)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from pnlclaw_types.errors import NotFoundError, PnLClawError, ErrorCode

from app.main import create_app


def _app():
    return create_app()


@pytest.mark.asyncio
async def test_pnlclaw_not_found_error():
    """PnLClawError (NotFoundError) should return 404 with unified body."""
    app = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/strategies/nonexistent")
    assert resp.status_code == 404
    body = resp.json()
    assert body["data"] is None
    assert body["error"]["code"] == "NOT_FOUND"
    assert "nonexistent" in body["error"]["message"]


@pytest.mark.asyncio
async def test_pnlclaw_service_unavailable():
    """SERVICE_UNAVAILABLE should return 503."""
    app = _app()
    # Market service is None by default → _require_market_service raises
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/markets")
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "SERVICE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_validation_error():
    """Pydantic validation errors should return 422 with details."""
    app = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # Missing required fields in strategy creation
        resp = await c.post("/api/v1/strategies", json={})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "errors" in body["error"]["details"]


@pytest.mark.asyncio
async def test_unknown_error_returns_500():
    """Unhandled exceptions should return 500 without leaking internals."""
    from fastapi import APIRouter

    app = _app()
    test_router = APIRouter()

    @test_router.get("/api/v1/test-crash")
    async def crash():
        raise RuntimeError("something broke internally")

    app.include_router(test_router)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/test-crash")
    assert resp.status_code == 500
    body = resp.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["message"] == "An internal error occurred"
    # Internal error details should NOT be leaked
    assert "something broke" not in body["error"]["message"]


@pytest.mark.asyncio
async def test_error_response_has_meta():
    """All error responses should include meta with request_id field."""
    app = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/strategies/nonexistent")
    body = resp.json()
    assert "meta" in body
    assert "request_id" in body["meta"]
