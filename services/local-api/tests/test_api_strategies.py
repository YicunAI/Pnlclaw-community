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
    _mod._strategy_versions.clear()
    yield
    _mod._strategies.clear()
    _mod._strategy_versions.clear()


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
    "tags": ["trend", "btc"],
    "source": "user",
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
    assert body["data"]["tags"] == ["trend", "btc"]
    assert body["data"]["source"] == "user"
    assert body["data"]["version"] == 1
    assert body["data"]["lifecycle_state"] == "draft"


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
async def test_list_strategies_filter_by_tags():
    app = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post("/api/v1/strategies", json=_SAMPLE)
        other = {**_SAMPLE, "name": "ETH Mean Reversion", "tags": ["mean-reversion", "eth"]}
        await c.post("/api/v1/strategies", json=other)

        resp = await c.get("/api/v1/strategies?tags=btc")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["name"] == "BTC SMA Cross"


@pytest.mark.asyncio
async def test_update_strategy_can_update_tags_and_source():
    app = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        create_resp = await c.post("/api/v1/strategies", json=_SAMPLE)
        sid = create_resp.json()["data"]["id"]

        resp = await c.put(
            f"/api/v1/strategies/{sid}",
            json={"tags": ["momentum"], "source": "ai_agent"},
        )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["tags"] == ["momentum"]
    assert data["source"] == "ai_agent"
    assert data["version"] == 2


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
async def test_list_strategy_versions():
    app = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        create_resp = await c.post("/api/v1/strategies", json=_SAMPLE)
        sid = create_resp.json()["data"]["id"]
        await c.put(f"/api/v1/strategies/{sid}", json={"description": "updated"})
        resp = await c.get(f"/api/v1/strategies/{sid}/versions")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) >= 2
    assert data[0]["version"] >= data[-1]["version"]


@pytest.mark.asyncio
async def test_deploy_rejected_when_no_rules():
    """deploy-paper returns deployment=None when entry/exit rules are empty."""
    app = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        create_resp = await c.post("/api/v1/strategies", json=_SAMPLE)
        sid = create_resp.json()["data"]["id"]
        await c.post(f"/api/v1/strategies/{sid}/confirm")
        deploy_resp = await c.post(f"/api/v1/strategies/{sid}/deploy-paper", json={"account_id": "paper-default"})
    assert deploy_resp.status_code == 200
    payload = deploy_resp.json()["data"]
    assert payload["deployment"] is None
    assert payload["runner_status"] == "failed"
    assert "no trading rules" in payload["runner_error"]


_DEPLOYABLE_SAMPLE = {
    **_SAMPLE,
    "name": "Deployable SMA Cross",
    "entry_rules": {"type": "sma_cross", "short": 10, "long": 50},
    "exit_rules": {"type": "take_profit", "pct": 0.05},
}


@pytest.mark.asyncio
async def test_confirm_and_deploy_strategy_to_paper():
    app = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        create_resp = await c.post("/api/v1/strategies", json=_DEPLOYABLE_SAMPLE)
        sid = create_resp.json()["data"]["id"]

        confirm_resp = await c.post(f"/api/v1/strategies/{sid}/confirm")
        assert confirm_resp.status_code == 200
        assert confirm_resp.json()["data"]["lifecycle_state"] == "confirmed"

        deploy_resp = await c.post(f"/api/v1/strategies/{sid}/deploy-paper", json={"account_id": "paper-default"})
    assert deploy_resp.status_code == 200
    payload = deploy_resp.json()["data"]
    assert payload["strategy"]["lifecycle_state"] in ("running", "confirmed")




@pytest.mark.asyncio
async def test_list_strategy_deployments():
    app = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        create_resp = await c.post("/api/v1/strategies", json=_DEPLOYABLE_SAMPLE)
        sid = create_resp.json()["data"]["id"]
        await c.post(f"/api/v1/strategies/{sid}/confirm")
        deploy_resp = await c.post(f"/api/v1/strategies/{sid}/deploy-paper", json={"account_id": "paper-default"})
        deploy_data = deploy_resp.json()["data"]
        if deploy_data.get("deployment") is None:
            pytest.skip("Runner not available in test environment; deployment was rejected")
        resp = await c.get("/api/v1/strategies/deployments/list?account_id=paper-default")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) >= 1
    assert data[0]["account_id"] == "paper-default"


@pytest.mark.asyncio
async def test_get_nonexistent_strategy_returns_error():
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
