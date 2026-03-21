"""pnlclaw_backtest — Event-driven backtesting engine for PnLClaw."""

from pnlclaw_backtest.broker import SimulatedBroker
from pnlclaw_backtest.commissions import CommissionModel, NoCommission, PercentageCommission
from pnlclaw_backtest.engine import BacktestConfig, BacktestEngine, BacktestError
from pnlclaw_backtest.metrics import compute_metrics
from pnlclaw_backtest.portfolio import Portfolio
from pnlclaw_backtest.protocols import StrategyRunner
from pnlclaw_backtest.reports import to_dict, to_json
from pnlclaw_backtest.slippage import FixedSlippage, NoSlippage, SlippageModel

__all__ = [
    "BacktestConfig",
    "BacktestEngine",
    "BacktestError",
    "CommissionModel",
    "FixedSlippage",
    "NoCommission",
    "NoSlippage",
    "PercentageCommission",
    "Portfolio",
    "SimulatedBroker",
    "SlippageModel",
    "StrategyRunner",
    "compute_metrics",
    "to_dict",
    "to_json",
]
