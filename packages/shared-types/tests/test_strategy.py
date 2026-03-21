"""Tests for pnlclaw_types.strategy — serialization/deserialization roundtrips."""

import json
from datetime import UTC, datetime

from pnlclaw_types.strategy import (
    BacktestMetrics,
    BacktestResult,
    Signal,
    StrategyConfig,
    StrategyType,
)
from pnlclaw_types.trading import OrderSide


class TestStrategyType:
    def test_values(self):
        assert set(StrategyType) == {
            StrategyType.SMA_CROSS,
            StrategyType.RSI_REVERSAL,
            StrategyType.MACD,
            StrategyType.CUSTOM,
        }


class TestStrategyConfig:
    def test_roundtrip(self):
        sc = StrategyConfig(
            id="strat-001",
            name="BTC SMA Cross",
            type=StrategyType.SMA_CROSS,
            symbols=["BTC/USDT"],
            interval="1h",
            parameters={"sma_short": 10, "sma_long": 50},
            entry_rules={"condition": "sma_short > sma_long"},
            exit_rules={"condition": "sma_short < sma_long"},
            risk_params={"stop_loss_pct": 0.02},
        )
        raw = sc.model_dump_json()
        restored = StrategyConfig.model_validate_json(raw)
        assert restored == sc

    def test_json_serializable(self):
        """StrategyConfig must be JSON-serializable (YAML-compatible structure)."""
        sc = StrategyConfig(
            id="strat-002",
            name="Custom",
            type=StrategyType.CUSTOM,
            symbols=["ETH/USDT"],
            interval="4h",
        )
        data = json.loads(sc.model_dump_json())
        assert isinstance(data, dict)
        assert data["id"] == "strat-002"
        assert data["symbols"] == ["ETH/USDT"]


class TestSignal:
    def test_roundtrip(self):
        s = Signal(
            strategy_id="strat-001",
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            strength=0.85,
            timestamp=1711000000000,
            reason="SMA 10 crossed above SMA 50",
        )
        raw = s.model_dump_json()
        restored = Signal.model_validate_json(raw)
        assert restored == s


class TestBacktestMetrics:
    def test_roundtrip(self):
        m = BacktestMetrics(
            total_return=0.15,
            annual_return=0.45,
            sharpe_ratio=1.8,
            max_drawdown=-0.08,
            win_rate=0.55,
            profit_factor=1.6,
            total_trades=42,
        )
        raw = m.model_dump_json()
        restored = BacktestMetrics.model_validate_json(raw)
        assert restored == m


class TestBacktestResult:
    def test_roundtrip(self):
        r = BacktestResult(
            id="bt-001",
            strategy_id="strat-001",
            start_date=datetime(2025, 1, 1, tzinfo=UTC),
            end_date=datetime(2025, 3, 31, 23, 59, 59, tzinfo=UTC),
            metrics=BacktestMetrics(
                total_return=0.15,
                annual_return=0.45,
                sharpe_ratio=1.8,
                max_drawdown=-0.08,
                win_rate=0.55,
                profit_factor=1.6,
                total_trades=42,
            ),
            equity_curve=[10000.0, 10050.0, 10500.0],
            trades_count=42,
            created_at=1711000000000,
        )
        raw = r.model_dump_json()
        restored = BacktestResult.model_validate_json(raw)
        assert restored == r
        assert restored.metrics.sharpe_ratio == 1.8
