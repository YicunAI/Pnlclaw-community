"""Tests for backtest feedback loop and suggestion application."""

from __future__ import annotations

from datetime import UTC, datetime

from pnlclaw_agent.feedback import (
    BacktestFeedbackLoop,
    StrategyImprovement,
    apply_suggestion,
)
from pnlclaw_agent.feedback.analyzer import (
    ISSUE_EXCESSIVE_DRAWDOWN,
    ISSUE_LOW_WIN_RATE,
    ISSUE_SHARPE_NEGATIVE,
    ISSUE_TOO_FEW_TRADES,
    ISSUE_TOO_MANY_TRADES,
)
from pnlclaw_strategy.models import EngineStrategyConfig
from pnlclaw_types.strategy import BacktestMetrics, BacktestResult, StrategyType


def _metrics(
    *,
    sharpe: float = 1.0,
    max_drawdown: float = -0.05,
    win_rate: float = 0.5,
    total_trades: int = 20,
) -> BacktestMetrics:
    return BacktestMetrics(
        total_return=0.1,
        annual_return=0.2,
        sharpe_ratio=sharpe,
        max_drawdown=max_drawdown,
        win_rate=win_rate,
        profit_factor=1.2,
        total_trades=total_trades,
    )


def _result(
    *,
    trades_count: int,
    metrics: BacktestMetrics,
) -> BacktestResult:
    return BacktestResult(
        id="bt-test",
        strategy_id="strat-1",
        start_date=datetime(2025, 1, 1, tzinfo=UTC),
        end_date=datetime(2025, 3, 1, tzinfo=UTC),
        metrics=metrics,
        equity_curve=[10000.0, 10100.0],
        trades_count=trades_count,
        created_at=1_711_000_000_000,
    )


def test_analyze_detects_sharpe_negative() -> None:
    loop = BacktestFeedbackLoop()
    r = _result(trades_count=20, metrics=_metrics(sharpe=-0.5))
    report = loop.analyze(r)
    assert ISSUE_SHARPE_NEGATIVE in report.issues
    assert any(s.category == "parameter_tuning" for s in report.suggestions)


def test_analyze_detects_excessive_drawdown() -> None:
    loop = BacktestFeedbackLoop()
    r = _result(trades_count=20, metrics=_metrics(max_drawdown=-0.35))
    report = loop.analyze(r)
    assert ISSUE_EXCESSIVE_DRAWDOWN in report.issues
    assert any(s.category == "risk" for s in report.suggestions)


def test_analyze_detects_low_win_rate() -> None:
    loop = BacktestFeedbackLoop()
    r = _result(trades_count=20, metrics=_metrics(win_rate=0.2))
    report = loop.analyze(r)
    assert ISSUE_LOW_WIN_RATE in report.issues
    assert any(s.category == "add_filter" for s in report.suggestions)


def test_analyze_detects_too_few_trades() -> None:
    loop = BacktestFeedbackLoop()
    r = _result(trades_count=3, metrics=_metrics(total_trades=3))
    report = loop.analyze(r)
    assert ISSUE_TOO_FEW_TRADES in report.issues
    assert any(s.category == "timeframe" for s in report.suggestions)


def test_analyze_detects_too_many_trades() -> None:
    loop = BacktestFeedbackLoop()
    r = _result(trades_count=600, metrics=_metrics(total_trades=600))
    report = loop.analyze(r)
    assert ISSUE_TOO_MANY_TRADES in report.issues
    assert any(s.category == "add_filter" for s in report.suggestions)


def test_suggestions_generated_for_each_issue_type() -> None:
    loop = BacktestFeedbackLoop()
    cases = [
        (ISSUE_SHARPE_NEGATIVE, _result(trades_count=20, metrics=_metrics(sharpe=-1.0))),
        (ISSUE_EXCESSIVE_DRAWDOWN, _result(trades_count=20, metrics=_metrics(max_drawdown=-0.4))),
        (ISSUE_LOW_WIN_RATE, _result(trades_count=20, metrics=_metrics(win_rate=0.1))),
        (ISSUE_TOO_FEW_TRADES, _result(trades_count=2, metrics=_metrics(total_trades=2))),
        (ISSUE_TOO_MANY_TRADES, _result(trades_count=600, metrics=_metrics(total_trades=600))),
    ]
    for expected_issue, res in cases:
        report = loop.analyze(res)
        assert expected_issue in report.issues
        assert report.suggestions, f"expected suggestions for {expected_issue}"


def test_apply_suggestion_merges_interval() -> None:
    cfg = EngineStrategyConfig(
        id="x",
        name="t",
        type=StrategyType.SMA_CROSS,
        symbols=["BTC/USDT"],
        interval="1h",
        parameters={"sma_short": 10, "sma_long": 50},
    )
    sug = StrategyImprovement(
        description="test",
        category="timeframe",
        suggested_changes={"interval": "4h"},
    )
    updated = apply_suggestion(cfg, sug)
    assert updated.interval == "4h"


def test_apply_suggestion_merges_parameters_dict() -> None:
    cfg = EngineStrategyConfig(
        id="x",
        name="t",
        type=StrategyType.SMA_CROSS,
        symbols=["BTC/USDT"],
        interval="1h",
        parameters={"sma_short": 10, "sma_long": 50},
    )
    sug = StrategyImprovement(
        description="tune",
        category="parameter_tuning",
        suggested_changes={"parameters": {"sma_short": 12}},
    )
    updated = apply_suggestion(cfg, sug)
    assert updated.parameters["sma_short"] == 12
    assert updated.parameters["sma_long"] == 50


def test_apply_suggestion_merges_risk_params() -> None:
    cfg = EngineStrategyConfig(
        id="x",
        name="t",
        type=StrategyType.SMA_CROSS,
        symbols=["BTC/USDT"],
        interval="1h",
        parameters={},
        risk_params={"max_position_pct": 0.1},
    )
    sug = StrategyImprovement(
        description="risk",
        category="risk",
        suggested_changes={"risk_params": {"stop_loss_pct": 0.02}},
    )
    updated = apply_suggestion(cfg, sug)
    assert updated.risk_params["stop_loss_pct"] == 0.02
    assert updated.risk_params["max_position_pct"] == 0.1
