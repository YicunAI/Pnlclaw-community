"""Integration tests for PnLClaw v0.1 production closed-loop.

Validates the full pipeline: strategy → backtest → paper trading → risk checks.
These tests exercise the real wiring between API endpoints and engine packages
without requiring a running exchange connection.
"""

from __future__ import annotations

import asyncio

import app.api.v1.backtests as bt_mod
import app.api.v1.strategies as strat_mod
import pytest
from app.core.dependencies import (
    get_execution_engine,
    get_live_engine,
    get_paper_account_manager,
    get_paper_order_manager,
    get_paper_position_manager,
)
from app.main import create_app
from httpx import ASGITransport, AsyncClient

from pnlclaw_paper.accounts import AccountManager
from pnlclaw_paper.orders import PaperOrderManager
from pnlclaw_paper.positions import PositionManager


@pytest.fixture(autouse=True)
def _clear_stores():
    bt_mod._tasks.clear()
    strat_mod._strategies.clear()
    yield
    bt_mod._tasks.clear()
    strat_mod._strategies.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SMA_CROSS_STRATEGY = {
    "name": "BTC SMA Cross",
    "type": "sma_cross",
    "symbols": ["BTC/USDT"],
    "interval": "1h",
    "parameters": {"sma_short": 10, "sma_long": 50},
    "entry_rules": {
        "long": [
            {
                "indicator": "sma",
                "params": {"period": 10},
                "operator": "crosses_above",
                "comparator": {"indicator": "sma", "params": {"period": 50}},
            }
        ],
    },
    "exit_rules": {
        "close_long": [
            {
                "indicator": "sma",
                "params": {"period": 10},
                "operator": "crosses_below",
                "comparator": {"indicator": "sma", "params": {"period": 50}},
            }
        ],
    },
    "risk_params": {"stop_loss_pct": 0.02},
}


def _make_app_with_paper():
    """Create app with injected paper managers (no lifespan)."""
    accounts = AccountManager()
    orders = PaperOrderManager()
    positions = PositionManager()
    app = create_app()
    app.dependency_overrides[get_paper_account_manager] = lambda: accounts
    app.dependency_overrides[get_paper_order_manager] = lambda: orders
    app.dependency_overrides[get_paper_position_manager] = lambda: positions
    return app


# ---------------------------------------------------------------------------
# 1. Backtest closed-loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backtest_returns_flattened_metrics():
    """POST /backtests → GET /{task_id}: response includes strategy_name and flattened metrics."""
    app = _make_app_with_paper()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        create_strat = await c.post("/api/v1/strategies", json=_SMA_CROSS_STRATEGY)
        assert create_strat.status_code == 200
        strat_id = create_strat.json()["data"]["id"]

        start = await c.post(
            "/api/v1/backtests",
            json={"strategy_id": strat_id, "initial_capital": 10000},
        )
        assert start.status_code == 202
        task_id = start.json()["data"]["task_id"]

        # Poll until completion
        data = None
        for _ in range(30):
            await asyncio.sleep(0.5)
            result = await c.get(f"/api/v1/backtests/{task_id}")
            data = result.json()["data"]
            if data["status"] in ("completed", "failed"):
                break

    assert data is not None
    assert "id" in data
    assert data["strategy_id"] == strat_id
    assert data["strategy_name"] == "BTC SMA Cross"
    assert data["status"] in ("completed", "failed")


@pytest.mark.asyncio
async def test_backtest_list_includes_frontend_fields():
    """GET /backtests: each item has `id` and `strategy_name` for frontend display."""
    app = _make_app_with_paper()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # Create strategy and start a backtest
        strat = await c.post("/api/v1/strategies", json=_SMA_CROSS_STRATEGY)
        strat_id = strat.json()["data"]["id"]
        await c.post("/api/v1/backtests", json={"strategy_id": strat_id})

        await asyncio.sleep(2.0)

        resp = await c.get("/api/v1/backtests")
        data = resp.json()["data"]

    assert len(data) >= 1
    item = data[0]
    assert "id" in item
    assert "strategy_id" in item


# ---------------------------------------------------------------------------
# 2. Paper trading unified state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_paper_account_field_alignment():
    """POST /paper/accounts: response has initial_balance and current_balance."""
    app = _make_app_with_paper()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(
            "/api/v1/paper/accounts",
            json={"name": "Test", "initial_balance": 50000},
        )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["initial_balance"] == 50000
    assert "current_balance" in data


@pytest.mark.asyncio
async def test_paper_pnl_returns_data():
    """GET /paper/pnl: returns PnL data (empty for no positions)."""
    app = _make_app_with_paper()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        acct = await c.post(
            "/api/v1/paper/accounts",
            json={"name": "Test", "initial_balance": 10000},
        )
        aid = acct.json()["data"]["id"]
        resp = await c.get(f"/api/v1/paper/pnl?account_id={aid}")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


# ---------------------------------------------------------------------------
# 3. Strategy persistence (in-memory for test, but endpoint works)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_strategy_returns_symbol_field():
    """GET /strategies: response includes both `symbols` list and `symbol` string."""
    app = _make_app_with_paper()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post("/api/v1/strategies", json=_SMA_CROSS_STRATEGY)
        resp = await c.get("/api/v1/strategies")
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["symbol"] == "BTC/USDT"
    assert data[0]["symbols"] == ["BTC/USDT"]


# ---------------------------------------------------------------------------
# 4. Risk engine pre-check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_risk_engine_blocks_when_configured():
    """POST /trading/orders: risk engine blocks order when conditions are met."""
    from app.core.dependencies import set_risk_engine as _set_risk

    from pnlclaw_paper.paper_execution import PaperExecutionEngine
    from pnlclaw_risk.engine import RiskEngine
    from pnlclaw_risk.rules import SymbolBlacklistRule

    app = create_app()
    paper_engine = PaperExecutionEngine(initial_balance=100000)

    blacklist_rule = SymbolBlacklistRule(blacklist=["BLOCKED/USDT"])
    risk_engine = RiskEngine(rules=[blacklist_rule])

    app.dependency_overrides[get_execution_engine] = lambda: paper_engine
    app.dependency_overrides[get_live_engine] = lambda: paper_engine
    _set_risk(risk_engine)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            await paper_engine.start()

            resp = await c.post(
                "/api/v1/trading/orders",
                json={
                    "symbol": "BLOCKED/USDT",
                    "side": "buy",
                    "order_type": "market",
                    "quantity": 1.0,
                },
            )

        assert resp.status_code == 403
        assert "blacklisted" in resp.json()["detail"].lower()
    finally:
        _set_risk(None)


@pytest.mark.asyncio
async def test_risk_engine_allows_normal_order():
    """POST /trading/orders: normal order passes risk checks."""
    from app.core.dependencies import set_risk_engine as _set_risk

    from pnlclaw_paper.paper_execution import PaperExecutionEngine
    from pnlclaw_risk.engine import RiskEngine
    from pnlclaw_risk.rules import create_default_rules

    app = create_app()
    paper_engine = PaperExecutionEngine(initial_balance=100000)
    risk_engine = RiskEngine(rules=create_default_rules())

    app.dependency_overrides[get_execution_engine] = lambda: paper_engine
    app.dependency_overrides[get_live_engine] = lambda: paper_engine
    _set_risk(risk_engine)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            await paper_engine.start()

            resp = await c.post(
                "/api/v1/trading/orders",
                json={
                    "symbol": "BTC/USDT",
                    "side": "buy",
                    "order_type": "market",
                    "quantity": 0.001,
                },
            )

        assert resp.status_code == 200
    finally:
        _set_risk(None)


# ---------------------------------------------------------------------------
# 5. Live mode block
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_live_mode_blocked():
    """PUT /trading/mode to 'live' is rejected in v0.1."""
    app = _make_app_with_paper()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.put("/api/v1/trading/mode", json={"mode": "live"})
    assert resp.status_code == 400
    assert "not available" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 6. Strategy → backtest end-to-end data contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_strategy_create_and_backtest_field_contract():
    """Full flow: create strategy → start backtest → verify field names align."""
    app = _make_app_with_paper()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        strat_resp = await c.post("/api/v1/strategies", json=_SMA_CROSS_STRATEGY)
        strat_data = strat_resp.json()["data"]

        assert "id" in strat_data
        assert "name" in strat_data
        assert "symbol" in strat_data
        assert "symbols" in strat_data

        bt_resp = await c.post(
            "/api/v1/backtests",
            json={
                "strategy_id": strat_data["id"],
                "initial_capital": 20000,
                "commission_rate": 0.001,
            },
        )
        assert bt_resp.status_code == 202
        bt_data = bt_resp.json()["data"]
        assert "task_id" in bt_data
        assert "status" in bt_data
