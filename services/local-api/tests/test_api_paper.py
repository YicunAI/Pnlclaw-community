"""Tests for paper trading endpoints (S3-L05)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.dependencies import (
    get_paper_account_manager,
    get_paper_order_manager,
    get_paper_position_manager,
)
from app.main import create_app

# Use real pnlclaw_paper managers for integration testing
from pnlclaw_paper.accounts import AccountManager
from pnlclaw_paper.orders import PaperOrderManager
from pnlclaw_paper.positions import PositionManager


@pytest.fixture()
def managers():
    return AccountManager(), PaperOrderManager(), PositionManager()


def _make_app(managers_tuple):
    accounts, orders, positions = managers_tuple
    app = create_app()
    app.dependency_overrides[get_paper_account_manager] = lambda: accounts
    app.dependency_overrides[get_paper_order_manager] = lambda: orders
    app.dependency_overrides[get_paper_position_manager] = lambda: positions
    return app


@pytest.mark.asyncio
async def test_create_account(managers):
    app = _make_app(managers)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/paper/accounts",
            json={"name": "Test Account", "initial_balance": 50000},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["name"] == "Test Account"
    assert body["data"]["initial_balance"] == 50000


@pytest.mark.asyncio
async def test_list_accounts(managers):
    app = _make_app(managers)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post("/api/v1/paper/accounts", json={"name": "A1", "initial_balance": 1000})
        resp = await c.get("/api/v1/paper/accounts")
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 1


@pytest.mark.asyncio
async def test_get_account(managers):
    app = _make_app(managers)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        create = await c.post(
            "/api/v1/paper/accounts", json={"name": "A1", "initial_balance": 1000}
        )
        aid = create.json()["data"]["id"]
        resp = await c.get(f"/api/v1/paper/accounts/{aid}")
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == aid


@pytest.mark.asyncio
async def test_get_account_not_found(managers):
    app = _make_app(managers)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get("/api/v1/paper/accounts/nonexistent")
    assert resp.status_code in (404, 500)


@pytest.mark.asyncio
async def test_place_order(managers):
    app = _make_app(managers)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        create = await c.post(
            "/api/v1/paper/accounts", json={"name": "A1", "initial_balance": 1000}
        )
        aid = create.json()["data"]["id"]

        resp = await c.post(
            "/api/v1/paper/orders",
            json={
                "account_id": aid,
                "symbol": "BTC/USDT",
                "side": "buy",
                "order_type": "market",
                "quantity": 0.1,
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["symbol"] == "BTC/USDT"
    assert body["data"]["side"] == "buy"
    assert body["data"]["status"] == "accepted"


@pytest.mark.asyncio
async def test_list_orders(managers):
    app = _make_app(managers)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        create = await c.post(
            "/api/v1/paper/accounts", json={"name": "A1", "initial_balance": 1000}
        )
        aid = create.json()["data"]["id"]
        await c.post(
            "/api/v1/paper/orders",
            json={
                "account_id": aid,
                "symbol": "BTC/USDT",
                "side": "buy",
                "order_type": "market",
                "quantity": 0.1,
            },
        )

        resp = await c.get(f"/api/v1/paper/orders?account_id={aid}")
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 1


@pytest.mark.asyncio
async def test_list_positions(managers):
    app = _make_app(managers)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        create = await c.post(
            "/api/v1/paper/accounts", json={"name": "A1", "initial_balance": 1000}
        )
        aid = create.json()["data"]["id"]
        resp = await c.get(f"/api/v1/paper/positions?account_id={aid}")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


@pytest.mark.asyncio
async def test_get_pnl(managers):
    app = _make_app(managers)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        create = await c.post(
            "/api/v1/paper/accounts", json={"name": "A1", "initial_balance": 1000}
        )
        aid = create.json()["data"]["id"]
        resp = await c.get(f"/api/v1/paper/pnl?account_id={aid}")
    assert resp.status_code == 200
    assert resp.json()["data"] == []
