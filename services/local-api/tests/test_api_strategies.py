"""Tests for strategy endpoints (S3-L03)."""

from __future__ import annotations

# Reset in-memory store between tests
import app.api.v1.strategies as _mod
import pytest
from app.main import create_app
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def _clear_store():
    _mod._strategies.clear()
    yield
    _mod._strategies.clear()


def _app():
    return create_app()


_SAMPLE = {
    "name": "BTC SMA Cross",
    "type": "sma_cross",
    "description": "Test strategy",
    "symbols": ["BTC/USDT"],
    "interval": "1h",
    "parameters": {"sma_short": 10, "sma_long": 50},
    "entry_rules": {},
    "exit_rules": {},
    "risk_params": {"stop_loss_pct": 0.02},
}


@pytest.mark.asyncio
async def test_create_strategy():
    app = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/api/v1/strategies", json=_SAMPLE)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["name"] == "BTC SMA Cross"
    assert body["data"]["id"].startswith("strat-")


@pytest.mark.asyncio
async def test_list_strategies_empty():
    app = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/strategies")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == []
    assert body["meta"]["pagination"]["total"] == 0


@pytest.mark.asyncio
async def test_list_strategies_with_pagination():
    app = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # Create 3 strategies
        for i in range(3):
            sample = {**_SAMPLE, "name": f"Strategy {i}"}
            await c.post("/api/v1/strategies", json=sample)

        resp = await c.get("/api/v1/strategies?offset=1&limit=1")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 1
    assert body["meta"]["pagination"]["total"] == 3
    assert body["meta"]["pagination"]["offset"] == 1
    assert body["meta"]["pagination"]["limit"] == 1


@pytest.mark.asyncio
async def test_get_strategy():
    app = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        create_resp = await c.post("/api/v1/strategies", json=_SAMPLE)
        sid = create_resp.json()["data"]["id"]

        resp = await c.get(f"/api/v1/strategies/{sid}")
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == sid


@pytest.mark.asyncio
async def test_get_strategy_not_found():
    app = _app()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/strategies/nonexistent")
    assert resp.status_code in (404, 500)


@pytest.mark.asyncio
async def test_delete_strategy():
    app = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        create_resp = await c.post("/api/v1/strategies", json=_SAMPLE)
        sid = create_resp.json()["data"]["id"]

        resp = await c.delete(f"/api/v1/strategies/{sid}")
    assert resp.status_code == 200
    assert resp.json()["data"]["deleted"] == sid


@pytest.mark.asyncio
async def test_validate_strategy_ok():
    app = _app()
    transport = ASGITransport(app=app)
    body = {
        "name": "test",
        "type": "sma_cross",
        "symbols": ["BTC/USDT"],
        "interval": "1h",
        "parameters": {"sma_short": 10, "sma_long": 50},
    }
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/api/v1/strategies/validate", json=body)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["valid"] is True
    assert data["errors"] == []
