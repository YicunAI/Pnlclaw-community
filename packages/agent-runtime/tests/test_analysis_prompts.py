"""Tests for server-side analysis prompt builder."""

from __future__ import annotations

from pnlclaw_agent.analysis_prompts import (
    INTENT_BACKTEST_EXPLAIN,
    INTENT_CLOSE_EVALUATION,
    INTENT_MULTI_TIMEFRAME,
    INTENT_TIMEFRAME_TRADE,
    VALID_INTENTS,
    build_analysis_prompt,
)


class TestBuildAnalysisPrompt:
    def test_invalid_intent_returns_none(self) -> None:
        assert build_analysis_prompt({}) is None
        assert build_analysis_prompt({"intent": "bogus"}) is None

    def test_multi_timeframe_basic(self) -> None:
        prompt = build_analysis_prompt(
            {
                "intent": INTENT_MULTI_TIMEFRAME,
                "symbol": "BTC/USDT",
                "exchange": "okx",
                "market_type": "futures",
                "mark_price": 66000,
            }
        )
        assert prompt is not None
        assert "BTC/USDT" in prompt
        assert "okx" in prompt
        assert "66000" in prompt
        assert "15分钟" in prompt
        assert "4小时" in prompt

    def test_multi_timeframe_with_positions(self) -> None:
        prompt = build_analysis_prompt(
            {
                "intent": INTENT_MULTI_TIMEFRAME,
                "symbol": "BTC/USDT",
                "exchange": "okx",
                "market_type": "futures",
                "mark_price": 66000,
                "contract_symbol": "BTC-USDT-SWAP",
                "positions": [
                    {
                        "symbol": "BTC-USDT-SWAP",
                        "pos_side": "long",
                        "leverage": 10,
                        "margin": 1000.0,
                        "quantity_base": 0.15,
                        "avg_entry_price": 65000.0,
                        "unrealized_pnl": 150.0,
                    },
                ],
            }
        )
        assert prompt is not None
        assert "用户当前持仓状态" in prompt
        assert "多单" in prompt
        assert "BTC-USDT-SWAP" in prompt
        assert "65000.00" in prompt

    def test_timeframe_trade(self) -> None:
        prompt = build_analysis_prompt(
            {
                "intent": INTENT_TIMEFRAME_TRADE,
                "symbol": "ETH/USDT",
                "exchange": "okx",
                "market_type": "futures",
                "timeframe": "15m",
                "mark_price": 3500,
            }
        )
        assert prompt is not None
        assert "15m" in prompt
        assert "ETH/USDT" in prompt
        assert "3500" in prompt
        assert "入场点位" in prompt

    def test_timeframe_trade_with_positions_adds_ref(self) -> None:
        prompt = build_analysis_prompt(
            {
                "intent": INTENT_TIMEFRAME_TRADE,
                "symbol": "BTC/USDT",
                "exchange": "okx",
                "market_type": "futures",
                "timeframe": "1h",
                "mark_price": 66000,
                "positions": [{"pos_side": "long", "leverage": 5, "margin": 500}],
            }
        )
        assert prompt is not None
        assert "结合我的持仓情况" in prompt

    def test_close_evaluation_with_positions(self) -> None:
        prompt = build_analysis_prompt(
            {
                "intent": INTENT_CLOSE_EVALUATION,
                "symbol": "BTC/USDT",
                "exchange": "okx",
                "market_type": "futures",
                "mark_price": 66000,
                "contract_symbol": "BTC-USDT-SWAP",
                "positions": [
                    {"pos_side": "short", "leverage": 20, "margin": 200},
                ],
            }
        )
        assert prompt is not None
        assert "平仓" in prompt
        assert "空单" in prompt
        assert "风险评估" in prompt

    def test_close_evaluation_no_positions(self) -> None:
        prompt = build_analysis_prompt(
            {
                "intent": INTENT_CLOSE_EVALUATION,
                "symbol": "SOL/USDT",
                "exchange": "okx",
                "market_type": "futures",
                "mark_price": 180,
            }
        )
        assert prompt is not None
        assert "没有找到活跃持仓" in prompt
        assert "SOL" in prompt
        assert "入场建议" in prompt

    def test_backtest_explain_prompt(self) -> None:
        prompt = build_analysis_prompt(
            {
                "intent": INTENT_BACKTEST_EXPLAIN,
                "backtest_id": "bt-123",
                "strategy_id": "strat-123",
                "strategy_name": "MACD Momentum",
                "symbol": "BTC/USDT",
                "timeframe": "1h",
                "metrics": {
                    "total_return": 0.12,
                    "annual_return": 0.45,
                    "sharpe_ratio": 1.8,
                    "max_drawdown": -0.08,
                    "win_rate": 0.55,
                    "profit_factor": 1.6,
                    "total_trades": 42,
                    "calmar_ratio": 5.6,
                    "sortino_ratio": 2.1,
                    "expectancy": 12.3,
                    "recovery_factor": 1.9,
                },
            }
        )
        assert prompt is not None
        assert "MACD Momentum" in prompt
        assert "bt-123" in prompt
        assert "最大回撤" in prompt
        assert "下一步应该优先优化什么" in prompt

        prompt = build_analysis_prompt({"intent": INTENT_MULTI_TIMEFRAME})
        assert prompt is not None
        assert "BTC/USDT" in prompt
        assert "未知" in prompt

    def test_all_intents_covered(self) -> None:
        for intent in VALID_INTENTS:
            prompt = build_analysis_prompt({"intent": intent, "mark_price": 100})
            assert prompt is not None, f"Intent {intent} returned None"

    def test_no_prompt_template_leaks_frontend_patterns(self) -> None:
        """Verify the generated prompts don't contain JS-style template syntax."""
        for intent in VALID_INTENTS:
            prompt = build_analysis_prompt(
                {
                    "intent": intent,
                    "symbol": "BTC/USDT",
                    "mark_price": 60000,
                }
            )
            assert prompt is not None
            assert "${" not in prompt
            assert "tickerSymbol" not in prompt
            assert "currentSymbolInfo" not in prompt
