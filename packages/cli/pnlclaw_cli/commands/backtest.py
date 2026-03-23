"""Backtest commands."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click
import pandas as pd

from pnlclaw_backtest.engine import BacktestConfig, BacktestEngine
from pnlclaw_storage.sqlite import AsyncSQLiteManager
from pnlclaw_strategy.compiler import compile as compile_strategy
from pnlclaw_strategy.models import load_strategy
from pnlclaw_strategy.runtime import StrategyRuntime


@click.group("backtest")
def backtest_group() -> None:
    """Run or list backtests."""


@backtest_group.command("run")
@click.argument("strategy_yaml", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--data",
    "data_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Parquet file with OHLCV (timestamp, open, high, low, close, volume).",
)
def backtest_run(strategy_yaml: Path, data_path: Path) -> None:
    """Run a backtest from STRATEGY_YAML using Parquet kline data."""
    try:
        strat = load_strategy(strategy_yaml)
        compiled = compile_strategy(strat)
        runtime = StrategyRuntime(compiled)
        df = pd.read_parquet(data_path)
        engine = BacktestEngine(BacktestConfig(strategy_id=strat.id))
        result = engine.run(strategy=runtime, data=df)
        m = result.metrics
        click.echo("Backtest complete")
        click.echo(f"  Total return: {m.total_return:.2%}")
        click.echo(f"  Sharpe:       {m.sharpe_ratio:.4f}")
        click.echo(f"  Max DD:       {m.max_drawdown:.2%}")
        click.echo(f"  Trade count:  {result.trades_count}")
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc


@backtest_group.command("list")
@click.option(
    "--db",
    "db_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="SQLite database path (defaults to config / ~/.pnlclaw/data/pnlclaw.db).",
)
def backtest_list(db_path: Path | None) -> None:
    """List stored backtest rows from SQLite (if any)."""
    from pnlclaw_core.config import load_config

    cfg = load_config()
    path = db_path or Path(cfg.db_path)
    if not path.is_absolute():
        path = path.resolve()
    if not path.is_file():
        click.echo("No database file found; nothing to list.")
        return

    async def _run() -> list[tuple]:
        mgr = AsyncSQLiteManager(path)
        await mgr.connect()
        rows = await mgr.execute(
            """
            SELECT id, strategy_id, start_date, end_date, trades_count, created_at
            FROM backtests
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (),
        )
        await mgr.close()
        out: list[tuple] = []
        for r in rows:
            out.append(
                (
                    r["id"],
                    r["strategy_id"],
                    r["start_date"],
                    r["end_date"],
                    r["trades_count"],
                    r["created_at"],
                )
            )
        return out

    try:
        tuples = asyncio.run(_run())
    except Exception as exc:
        raise click.ClickException(f"Could not read backtests: {exc}") from exc

    if not tuples:
        click.echo("No backtests stored in the database.")
        return

    click.echo(f"{'ID':<14} {'Strategy':<18} {'Trades':<8} {'Created'}")
    for bid, sid, _sdt, _edt, tc, cat in tuples:
        click.echo(f"{bid:<14} {sid:<18} {tc:<8} {cat}")
