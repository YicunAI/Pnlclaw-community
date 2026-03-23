"""End-to-end integration tests across strategy, backtest, paper, risk, agent, market, storage."""

from __future__ import annotations

import asyncio
import math
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from pnlclaw_agent.context.manager import ContextManager
from pnlclaw_agent.prompt_builder import AgentContext
from pnlclaw_agent.runtime import AgentRuntime
from pnlclaw_agent.tool_catalog import ToolCatalog
from pnlclaw_agent.tools.base import BaseTool, ToolResult
from pnlclaw_backtest.engine import BacktestConfig, BacktestEngine
from pnlclaw_market.state_engine import MarketStateEngine
from pnlclaw_paper.decision_pipeline import DecisionPipeline, PipelineAction, PipelineConfig
from pnlclaw_paper.orders import PaperOrderManager
from pnlclaw_risk.engine import RiskEngine
from pnlclaw_risk.rules import DailyLossLimitRule
from pnlclaw_storage.repositories.backtests import BacktestRepository
from pnlclaw_storage.repositories.strategies import StrategyRepository
from pnlclaw_storage.sqlite import AsyncSQLiteManager
from pnlclaw_strategy.compiler import compile as compile_strategy
from pnlclaw_strategy.models import load_strategy
from pnlclaw_strategy.runtime import StrategyRuntime
from pnlclaw_types.agent import AgentStreamEventType, TradeIntent
from pnlclaw_types.market import KlineEvent
from pnlclaw_types.risk import RiskLevel as RiskLevelEnum
from pnlclaw_types.strategy import (
    BacktestMetrics,
    BacktestResult,
    Signal,
    StrategyConfig,
    StrategyType,
)
from pnlclaw_types.trading import OrderSide, OrderType

REPO_ROOT = Path(__file__).resolve().parents[2]
SMA_TEMPLATE = REPO_ROOT / "packages/strategy-engine/pnlclaw_strategy/templates/sma_cross.yaml"


class _IntegrationEchoTool(BaseTool):
    @property
    def name(self) -> str:
        return "integration_echo"

    @property
    def description(self) -> str:
        return "Echo integration test message."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"msg": {"type": "string"}},
            "required": ["msg"],
        }

    @property
    def risk_level(self):
        return RiskLevelEnum.SAFE

    def execute(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(output=str(args.get("msg", "")), error=None)


def test_strategy_compile_backtest_e2e(demo_data: pd.DataFrame) -> None:
    cfg = load_strategy(SMA_TEMPLATE)
    compiled = compile_strategy(cfg)
    runtime = StrategyRuntime(compiled, max_bars=2000)
    engine = BacktestEngine(
        config=BacktestConfig(initial_cash=10_000.0, strategy_id=cfg.id),
    )
    result = engine.run(strategy=runtime, data=demo_data)

    assert result.metrics.total_trades > 0
    assert math.isfinite(result.metrics.sharpe_ratio)
    assert len(result.equity_curve) == len(demo_data)


def test_paper_trading_decision_pipeline(
    paper_account,
    risk_engine,
) -> None:
    order_mgr = PaperOrderManager()
    pipeline = DecisionPipeline(
        risk_engine=risk_engine,
        order_manager=order_mgr,
        config=PipelineConfig(
            default_account_id=paper_account.id,
            min_order_interval_seconds=0.0,
            default_quantity=0.01,
        ),
        risk_context_provider=lambda: {
            "total_equity": paper_account.current_balance,
            "positions": {},
            "daily_realized_pnl": 0.0,
            "last_trade_times": {},
        },
    )
    sig = Signal(
        strategy_id="int-test",
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        strength=0.9,
        timestamp=int(time.time() * 1000),
        reason="integration BUY",
    )
    out = pipeline.process_signal(sig)
    assert out.action in (PipelineAction.EXECUTED, PipelineAction.BLOCKED)
    if out.action == PipelineAction.EXECUTED:
        assert out.order_id is not None
    else:
        assert "Risk" in out.reason or "risk" in out.reason.lower()


def test_risk_engine_blocks_excessive_loss() -> None:
    engine = RiskEngine([DailyLossLimitRule(max_daily_loss_pct=0.001)])
    intent = TradeIntent(
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        quantity=0.01,
        price=50_000.0,
        order_type=OrderType.MARKET,
        reasoning="integration",
        confidence=0.5,
        risk_params={},
        timestamp=int(time.time() * 1000),
    )
    ctx = {
        "total_equity": 10_000.0,
        "daily_realized_pnl": -10.0,
    }
    decision = engine.pre_check(intent, ctx)
    assert decision.allowed is False
    assert "daily_loss_limit" in decision.rule_id


def test_agent_tool_call_with_mock_llm(mock_llm) -> None:
    catalog = ToolCatalog()
    catalog.register(_IntegrationEchoTool())

    runtime = AgentRuntime(
        llm=mock_llm,
        tool_catalog=catalog,
        context_manager=ContextManager(),
        prompt_context=AgentContext(available_tools=catalog.get_tool_definitions()),
        max_tool_rounds=5,
    )

    async def _collect() -> list:
        events = []
        async for ev in runtime.process_message("run echo"):
            events.append(ev)
        return events

    events = asyncio.run(_collect())
    types = {e.type for e in events}
    assert AgentStreamEventType.TOOL_CALL in types
    assert AgentStreamEventType.TOOL_RESULT in types


def test_market_state_analysis(demo_data: pd.DataFrame) -> None:
    klines: list[KlineEvent] = []
    for row in demo_data.itertuples(index=False):
        klines.append(
            KlineEvent(
                exchange="backtest",
                symbol="BTC/USDT",
                timestamp=int(row.timestamp),
                interval="1h",
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
                closed=True,
            )
        )
    engine = MarketStateEngine()
    state = engine.analyze("BTC/USDT", klines)
    assert state.regime.value
    assert state.volatility >= 0.0


def test_storage_crud_roundtrip() -> None:
    async def _run() -> None:
        db = AsyncSQLiteManager(":memory:")
        await db.connect()
        try:
            strat_repo = StrategyRepository(db)
            strat = StrategyConfig(
                id="int-strat-1",
                name="Integration Strategy",
                type=StrategyType.SMA_CROSS,
                description="test",
                symbols=["BTC/USDT"],
                interval="1h",
                parameters={"a": 1},
                entry_rules={},
                exit_rules={},
                risk_params={},
            )
            sid = await strat_repo.save(strat)
            assert sid == strat.id
            loaded = await strat_repo.get(sid)
            assert loaded is not None
            assert loaded.model_dump() == strat.model_dump()

            bt_repo = BacktestRepository(db)
            metrics = BacktestMetrics(
                total_return=0.01,
                annual_return=0.1,
                sharpe_ratio=1.0,
                max_drawdown=-0.02,
                win_rate=0.5,
                profit_factor=1.2,
                total_trades=3,
            )
            bt = BacktestResult(
                id="int-bt-1",
                strategy_id=sid,
                start_date=datetime(2025, 1, 1, tzinfo=UTC),
                end_date=datetime(2025, 1, 31, tzinfo=UTC),
                metrics=metrics,
                equity_curve=[10_000.0, 10_050.0, 10_020.0],
                trades_count=3,
                created_at=1_700_000_000_000,
            )
            bid = await bt_repo.save(bt)
            assert bid == bt.id
            bt_loaded = await bt_repo.get(bid)
            assert bt_loaded is not None
            assert bt_loaded.model_dump() == bt.model_dump()
        finally:
            await db.close()

    asyncio.run(_run())
