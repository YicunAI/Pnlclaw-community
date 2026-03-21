"""Golden file regression test for backtest-engine.

Uses deterministic BTC data + SMA(20,50) crossover strategy to produce
a fixed result.  The result is compared against a golden file.  Any code
change that alters the golden file output is a regression.

To regenerate the golden file (e.g. after an intentional algorithm change):

    pytest tests/test_golden_sma_cross.py --regenerate-golden

"""

from __future__ import annotations

import json
import pathlib
from collections import deque

import pytest

from pnlclaw_types.market import KlineEvent
from pnlclaw_types.strategy import Signal
from pnlclaw_types.trading import OrderSide

from pnlclaw_backtest.engine import BacktestConfig, BacktestEngine
from pnlclaw_backtest.commissions import NoCommission
from pnlclaw_backtest.reports import to_dict
from pnlclaw_backtest.slippage import NoSlippage
from tests.fixtures.generate_data import generate_deterministic_btc_data

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"
GOLDEN_FILE = FIXTURES_DIR / "golden_sma_cross.json"


# ---------------------------------------------------------------------------
# SMA(20,50) Crossover strategy — deterministic, no external dependencies
# ---------------------------------------------------------------------------


class SmaCrossStrategy:
    """Simple SMA crossover strategy for regression testing.

    Emits BUY when SMA(short) crosses above SMA(long).
    Emits SELL when SMA(short) crosses below SMA(long).
    """

    def __init__(self, short_period: int = 20, long_period: int = 50) -> None:
        self._short_period = short_period
        self._long_period = long_period
        self._closes: deque[float] = deque(maxlen=long_period)
        self._prev_short: float | None = None
        self._prev_long: float | None = None

    def on_kline(self, event: KlineEvent) -> Signal | None:
        self._closes.append(event.close)

        if len(self._closes) < self._long_period:
            return None

        closes = list(self._closes)
        sma_short = sum(closes[-self._short_period :]) / self._short_period
        sma_long = sum(closes) / self._long_period

        signal = None
        if self._prev_short is not None and self._prev_long is not None:
            # Crossover detection
            prev_above = self._prev_short > self._prev_long
            curr_above = sma_short > sma_long

            if curr_above and not prev_above:
                signal = Signal(
                    strategy_id="sma_cross_20_50",
                    symbol=event.symbol,
                    side=OrderSide.BUY,
                    strength=1.0,
                    timestamp=event.timestamp,
                    reason=f"SMA({self._short_period}) crossed above SMA({self._long_period})",
                )
            elif not curr_above and prev_above:
                signal = Signal(
                    strategy_id="sma_cross_20_50",
                    symbol=event.symbol,
                    side=OrderSide.SELL,
                    strength=1.0,
                    timestamp=event.timestamp,
                    reason=f"SMA({self._short_period}) crossed below SMA({self._long_period})",
                )

        self._prev_short = sma_short
        self._prev_long = sma_long
        return signal

    def reset(self) -> None:
        self._closes.clear()
        self._prev_short = None
        self._prev_long = None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _run_golden_backtest() -> dict:
    """Run the canonical SMA(20,50) backtest with deterministic data."""
    df = generate_deterministic_btc_data(n_bars=200, seed=42)

    config = BacktestConfig(
        initial_cash=10_000.0,
        commission=NoCommission(),
        slippage=NoSlippage(),
        strategy_id="sma_cross_20_50",
    )
    engine = BacktestEngine(config=config)
    strategy = SmaCrossStrategy(short_period=20, long_period=50)
    result = engine.run(strategy=strategy, data=df)

    # Build a reproducible dict (strip non-deterministic fields)
    report = to_dict(result)
    # Remove non-deterministic fields
    report.pop("id", None)
    report.pop("created_at", None)
    return report


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--regenerate-golden",
        action="store_true",
        default=False,
        help="Regenerate the golden file instead of comparing against it.",
    )


class TestGoldenSmaCross:
    def test_golden_file_matches(self, request: pytest.FixtureRequest) -> None:
        """Compare current backtest output against the golden file."""
        result = _run_golden_backtest()

        if request.config.getoption("--regenerate-golden", default=False):
            FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
            GOLDEN_FILE.write_text(json.dumps(result, indent=2, default=str))
            pytest.skip("Golden file regenerated.")
            return

        if not GOLDEN_FILE.exists():
            # Auto-generate on first run
            FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
            GOLDEN_FILE.write_text(json.dumps(result, indent=2, default=str))
            # Still compare — should pass trivially
            golden = result
        else:
            golden = json.loads(GOLDEN_FILE.read_text())

        # Compare metrics
        for key in golden["metrics"]:
            assert result["metrics"][key] == pytest.approx(
                golden["metrics"][key], abs=1e-6
            ), f"Metric '{key}' differs: got {result['metrics'][key]}, expected {golden['metrics'][key]}"

        # Compare equity curve length
        assert len(result["equity_curve"]) == len(golden["equity_curve"])

        # Compare equity curve values
        for i, (actual, expected) in enumerate(
            zip(result["equity_curve"], golden["equity_curve"])
        ):
            assert actual == pytest.approx(
                expected, abs=1e-4
            ), f"Equity curve point {i} differs: got {actual}, expected {expected}"

        # Compare trade count
        assert result["trades_count"] == golden["trades_count"]

    def test_deterministic_across_runs(self) -> None:
        """Two runs with the same seed must produce identical results."""
        r1 = _run_golden_backtest()
        r2 = _run_golden_backtest()

        assert r1["metrics"] == r2["metrics"]
        assert r1["equity_curve"] == r2["equity_curve"]
        assert r1["trades_count"] == r2["trades_count"]

    def test_has_trades(self) -> None:
        """The SMA(20,50) strategy on 200 bars should produce at least 1 trade."""
        result = _run_golden_backtest()
        assert result["trades_count"] > 0, "Expected at least one trade from SMA cross strategy"
