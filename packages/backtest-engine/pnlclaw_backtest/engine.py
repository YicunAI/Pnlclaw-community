"""Backtest main engine — event-driven kline-by-kline simulation.

Usage::

    engine = BacktestEngine(config=BacktestConfig(...))
    result = engine.run(strategy=my_strategy, data=kline_list)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pandas as pd

from pnlclaw_backtest.broker import SimulatedBroker
from pnlclaw_backtest.commissions import CommissionModel, NoCommission
from pnlclaw_backtest.metrics import compute_metrics
from pnlclaw_backtest.portfolio import Portfolio
from pnlclaw_backtest.protocols import StrategyRunner
from pnlclaw_backtest.slippage import NoSlippage, SlippageModel
from pnlclaw_types.market import KlineEvent
from pnlclaw_types.strategy import BacktestResult
from pnlclaw_types.trading import Order, OrderSide, OrderType


class BacktestError(Exception):
    """Raised when a backtest run encounters an unrecoverable error."""


@dataclass(frozen=True)
class BacktestConfig:
    """Configuration for a single backtest run.

    Attributes:
        initial_cash: Starting cash balance (quote currency).
        commission: Commission model applied to each fill.
        slippage: Slippage model applied to each fill.
        trade_on_close: If True, market orders fill at the kline close price.
        strategy_id: Optional override; otherwise generated.
    """

    initial_cash: float = 10_000.0
    commission: CommissionModel = field(default_factory=NoCommission)
    slippage: SlippageModel = field(default_factory=NoSlippage)
    trade_on_close: bool = True
    strategy_id: str = ""


def _klines_from_dataframe(df: pd.DataFrame) -> list[KlineEvent]:
    """Convert a pandas DataFrame to a list of KlineEvent.

    Expected columns: timestamp, open, high, low, close, volume.
    Optional columns: exchange, symbol, interval, closed.
    """
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise BacktestError(f"DataFrame missing required columns: {missing}")

    events: list[KlineEvent] = []
    for row in df.itertuples(index=False):
        events.append(
            KlineEvent(
                exchange=getattr(row, "exchange", "backtest"),
                symbol=getattr(row, "symbol", "BTC/USDT"),
                timestamp=int(row.timestamp),
                interval=getattr(row, "interval", "1h"),
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
                closed=getattr(row, "closed", True),
            )
        )
    return events


class BacktestEngine:
    """Event-driven backtesting engine.

    Pushes kline bars one by one to a ``StrategyRunner``.  When the strategy
    emits a ``Signal``, the engine converts it to an ``Order``, routes it
    through a ``SimulatedBroker``, and updates the ``Portfolio``.

    Args:
        config: Backtest configuration.
    """

    def __init__(self, config: BacktestConfig | None = None) -> None:
        self._config = config or BacktestConfig()

    def run(
        self,
        strategy: StrategyRunner,
        data: pd.DataFrame | list[KlineEvent],
    ) -> BacktestResult:
        """Execute a full backtest.

        Args:
            strategy: A strategy implementing the ``StrategyRunner`` protocol.
            data: Kline data as a DataFrame or list of KlineEvent.

        Returns:
            A fully populated ``BacktestResult``.

        Raises:
            BacktestError: If the data is empty or invalid.
        """
        # --- Prepare klines -------------------------------------------------
        if isinstance(data, pd.DataFrame):
            klines = _klines_from_dataframe(data)
        else:
            klines = list(data)

        if not klines:
            raise BacktestError("No kline data provided for backtest.")

        # --- Initialise components ------------------------------------------
        strategy.reset()

        portfolio = Portfolio(initial_cash=self._config.initial_cash)
        broker = SimulatedBroker(
            slippage=self._config.slippage,
            commission=self._config.commission,
        )

        trades: list[dict] = []  # completed round-trip trade records
        _open_side: OrderSide | None = None  # track current position direction
        _entry_price: float = 0.0
        _entry_ts: int = 0
        _entry_fee: float = 0.0

        strategy_id = self._config.strategy_id or "backtest"

        # --- Event loop -----------------------------------------------------
        for kline in klines:
            signal = strategy.on_kline(kline)

            if signal is not None:
                # Determine if this signal closes an existing position or opens new
                current_qty = portfolio.get_position_quantity(kline.symbol)

                if current_qty > 0 and signal.side == OrderSide.SELL:
                    # Close long position
                    order = Order(
                        id=f"ord-{uuid.uuid4().hex[:8]}",
                        symbol=kline.symbol,
                        side=OrderSide.SELL,
                        type=OrderType.MARKET,
                        quantity=current_qty,
                        created_at=kline.timestamp,
                        updated_at=kline.timestamp,
                    )
                    fill = broker.execute(order, kline)
                    if fill is not None:
                        portfolio.apply_fill(fill, OrderSide.SELL)
                        trades.append(
                            {
                                "side": "long",
                                "entry_price": _entry_price,
                                "exit_price": fill.price,
                                "quantity": fill.quantity,
                                "pnl": (
                                (fill.price - _entry_price) * fill.quantity
                                - _entry_fee
                                - fill.fee
                            ),
                                "entry_time": _entry_ts,
                                "exit_time": kline.timestamp,
                            }
                        )
                        _open_side = None

                elif current_qty == 0 and signal.side == OrderSide.BUY:
                    # Open long position — size = fraction of available cash
                    price_est = kline.close
                    affordable_qty = portfolio.cash / price_est * 0.95  # keep 5% buffer
                    if affordable_qty > 0:
                        order = Order(
                            id=f"ord-{uuid.uuid4().hex[:8]}",
                            symbol=kline.symbol,
                            side=OrderSide.BUY,
                            type=OrderType.MARKET,
                            quantity=affordable_qty,
                            created_at=kline.timestamp,
                            updated_at=kline.timestamp,
                        )
                        fill = broker.execute(order, kline)
                        if fill is not None:
                            portfolio.apply_fill(fill, OrderSide.BUY)
                            _open_side = OrderSide.BUY
                            _entry_price = fill.price
                            _entry_ts = kline.timestamp
                            _entry_fee = fill.fee

            # Update equity at end of each bar
            portfolio.update_equity(kline.symbol, kline.close)

        # --- Build result ----------------------------------------------------
        equity_curve = portfolio.get_equity_curve()
        metrics = compute_metrics(equity_curve, trades)

        start_dt = datetime.fromtimestamp(klines[0].timestamp / 1000, tz=UTC)
        end_dt = datetime.fromtimestamp(klines[-1].timestamp / 1000, tz=UTC)

        return BacktestResult(
            id=f"bt-{uuid.uuid4().hex[:8]}",
            strategy_id=strategy_id,
            start_date=start_dt,
            end_date=end_dt,
            metrics=metrics,
            equity_curve=equity_curve,
            trades_count=len(trades),
            created_at=int(time.time() * 1000),
        )
