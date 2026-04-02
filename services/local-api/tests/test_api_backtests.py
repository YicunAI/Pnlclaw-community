"""Tests for backtest endpoints (S3-L04)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import app.api.v1.backtests as _mod
import pytest
from app.main import create_app
from httpx import ASGITransport, AsyncClient

from pnlclaw_types.strategy import BacktestMetrics, BacktestResult


@pytest.fixture(autouse=True)
def _clear_store():
    _mod._tasks.clear()
    yield
    _mod._tasks.clear()


def _make_result(id: str = "bt-001", strategy_id: str = "strat-001") -> BacktestResult:
    return BacktestResult(
        id=id,
        strategy_id=strategy_id,
        start_date=datetime(2025, 1, 1, tzinfo=UTC),
        end_date=datetime(2025, 3, 31, tzinfo=UTC),
        metrics=BacktestMetrics(
            total_return=0.15,
            annual_return=0.45,
            sharpe_ratio=1.8,
            max_drawdown=-0.08,
            win_rate=0.55,
            profit_factor=1.6,
            total_trades=42,
            calmar_ratio=5.6,
            sortino_ratio=2.1,
            expectancy=12.3,
            recovery_factor=1.9,
        ),
        equity_curve=[10000.0, 10100.0, 10500.0],
        drawdown_curve=[0.0, 0.0, -0.02],
        trades=[{"pnl": 10.0, "side": "buy", "timestamp": 1711000000000}],
        trades_count=1,
        created_at=1711000000000,
    )


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
async def test_get_backtest_from_shared_store():
    app = _app()
    transport = ASGITransport(app=app)
    result = _make_result("bt-shared", "strat-shared")
    from pnlclaw_agent.tools.strategy_tools import get_results_store

    get_results_store().clear()
    get_results_store()[result.id] = result
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/v1/backtests/bt-shared")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "completed"
        assert data["annual_return"] == 0.45
        assert data["drawdown_curve"] == [0.0, 0.0, -0.02]
        assert len(data["trades"]) == 1
        assert data["result"]["metrics"]["calmar_ratio"] == 5.6
    finally:
        get_results_store().clear()


@pytest.mark.asyncio
async def test_list_backtests_includes_shared_store_results():
    app = _app()
    transport = ASGITransport(app=app)
    result = _make_result("bt-shared-list", "s1")
    from pnlclaw_agent.tools.strategy_tools import get_results_store

    get_results_store().clear()
    get_results_store()[result.id] = result
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/api/v1/backtests?strategy_id=s1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["id"] == "bt-shared-list"
        assert data[0]["status"] == "completed"
    finally:
        get_results_store().clear()


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
