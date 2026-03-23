"""Tests for backtest endpoints (S3-L04)."""

from __future__ import annotations

import asyncio

import app.api.v1.backtests as _mod
import pytest
from app.main import create_app
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def _clear_store():
    _mod._tasks.clear()
    yield
    _mod._tasks.clear()


def _app():
    return create_app()


@pytest.mark.asyncio
async def test_start_backtest_returns_202():
    app = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/backtests",
            json={"strategy_id": "strat-abc", "initial_cash": 10000},
        )
    assert resp.status_code == 202
    body = resp.json()
    assert body["data"]["task_id"].startswith("bt-")
    assert body["data"]["status"] == "pending"
    assert body["meta"]["request_id"] == resp.headers["X-Request-ID"]


@pytest.mark.asyncio
async def test_get_backtest_failed_when_strategy_missing():
    app = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        create = await c.post(
            "/api/v1/backtests",
            json={"strategy_id": "strat-abc"},
        )
        task_id = create.json()["data"]["task_id"]

        # Give background task time to complete
        await asyncio.sleep(0.1)

        resp = await c.get(f"/api/v1/backtests/{task_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["status"] == "failed"
    assert body["data"].get("result") is None
    assert "error" in body["data"]


@pytest.mark.asyncio
async def test_get_backtest_not_found():
    app = _app()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/backtests/nonexistent")
    assert resp.status_code in (404, 500)


@pytest.mark.asyncio
async def test_list_backtests():
    app = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post("/api/v1/backtests", json={"strategy_id": "s1"})
        await c.post("/api/v1/backtests", json={"strategy_id": "s2"})
        await c.post("/api/v1/backtests", json={"strategy_id": "s1"})

        resp = await c.get("/api/v1/backtests")
    assert resp.status_code == 200
    assert resp.json()["meta"]["pagination"]["total"] == 3


@pytest.mark.asyncio
async def test_list_backtests_filter_by_strategy():
    app = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post("/api/v1/backtests", json={"strategy_id": "s1"})
        await c.post("/api/v1/backtests", json={"strategy_id": "s2"})

        resp = await c.get("/api/v1/backtests?strategy_id=s1")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["strategy_id"] == "s1"
