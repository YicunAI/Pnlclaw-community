"""Tests for S2-E08: strategy templates (sma_cross.yaml + rsi_reversal.yaml).

Verifies that both YAML templates can be loaded, compiled, and executed
through the full pipeline.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pnlclaw_strategy.compiler import CompiledStrategy, compile
from pnlclaw_strategy.models import EngineStrategyConfig, load_strategy
from pnlclaw_strategy.runtime import StrategyRuntime
from pnlclaw_types.market import KlineEvent


TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "pnlclaw_strategy" / "templates"


class TestSMACrossTemplate:
    """Test sma_cross.yaml template."""

    def test_load(self) -> None:
        config = load_strategy(TEMPLATES_DIR / "sma_cross.yaml")
        assert isinstance(config, EngineStrategyConfig)
        assert config.id == "template-sma-cross"
        assert config.type.value == "sma_cross"
        assert "BTC/USDT" in config.symbols

    def test_compile(self) -> None:
        config = load_strategy(TEMPLATES_DIR / "sma_cross.yaml")
        compiled = compile(config)
        assert isinstance(compiled, CompiledStrategy)
        assert len(compiled.long_entry_conditions) == 1
        assert len(compiled.close_long_conditions) == 1

    def test_run(self) -> None:
        config = load_strategy(TEMPLATES_DIR / "sma_cross.yaml")
        compiled = compile(config)
        rt = StrategyRuntime(compiled)

        # Feed enough klines to produce indicator values
        for i in range(60):
            kline = KlineEvent(
                exchange="binance",
                symbol="BTC/USDT",
                timestamp=i * 3600000,
                interval="1h",
                open=100.0 + i,
                high=101.0 + i,
                low=99.0 + i,
                close=100.0 + i,
                volume=1000.0,
                closed=True,
            )
            rt.on_kline(kline)

        assert rt.bar_count == 60

    def test_risk_params_loaded(self) -> None:
        config = load_strategy(TEMPLATES_DIR / "sma_cross.yaml")
        assert config.parsed_risk_params.stop_loss_pct == 0.03
        assert config.parsed_risk_params.take_profit_pct == 0.06


class TestRSIReversalTemplate:
    """Test rsi_reversal.yaml template."""

    def test_load(self) -> None:
        config = load_strategy(TEMPLATES_DIR / "rsi_reversal.yaml")
        assert isinstance(config, EngineStrategyConfig)
        assert config.id == "template-rsi-reversal"
        assert config.type.value == "rsi_reversal"

    def test_compile(self) -> None:
        config = load_strategy(TEMPLATES_DIR / "rsi_reversal.yaml")
        compiled = compile(config)
        assert isinstance(compiled, CompiledStrategy)
        assert len(compiled.long_entry_conditions) == 1
        assert len(compiled.close_long_conditions) == 1
        # RSI uses numeric comparators
        cond = compiled.long_entry_conditions[0]
        assert cond.comparator_value == 30.0

    def test_run_with_downtrend(self) -> None:
        """Feed declining prices to trigger RSI < 30 buy signal."""
        config = load_strategy(TEMPLATES_DIR / "rsi_reversal.yaml")
        compiled = compile(config)
        rt = StrategyRuntime(compiled)
        signals = []

        for i in range(30):
            kline = KlineEvent(
                exchange="binance",
                symbol="BTC/USDT",
                timestamp=i * 3600000,
                interval="1h",
                open=100.0 - i * 2,
                high=101.0 - i * 2,
                low=98.0 - i * 2,
                close=100.0 - i * 2,
                volume=1000.0,
                closed=True,
            )
            signal = rt.on_kline(kline)
            if signal:
                signals.append(signal)

        # Should have a buy signal from RSI going below 30
        buy_signals = [s for s in signals if s.side.value == "buy"]
        assert len(buy_signals) >= 1

    def test_risk_params_loaded(self) -> None:
        config = load_strategy(TEMPLATES_DIR / "rsi_reversal.yaml")
        assert config.parsed_risk_params.stop_loss_pct == 0.02


class TestEndToEndPipeline:
    """Test full pipeline: YAML → load → compile → runtime → signal."""

    @pytest.mark.parametrize("template_name", ["sma_cross.yaml", "rsi_reversal.yaml"])
    def test_template_loads_and_compiles(self, template_name: str) -> None:
        config = load_strategy(TEMPLATES_DIR / template_name)
        compiled = compile(config)
        rt = StrategyRuntime(compiled)
        assert rt.position == "flat"
        assert rt.bar_count == 0
