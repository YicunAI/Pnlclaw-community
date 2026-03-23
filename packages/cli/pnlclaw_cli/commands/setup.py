"""Interactive setup wizard for PnLClaw."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import click
import pandas as pd
import yaml

from pnlclaw_backtest.engine import BacktestConfig, BacktestEngine
from pnlclaw_cli.constants import SCHEMA_VERSION, cli_version
from pnlclaw_storage.sqlite import DEFAULT_DB_PATH, AsyncSQLiteManager
from pnlclaw_strategy.compiler import compile as compile_strategy
from pnlclaw_strategy.models import load_strategy
from pnlclaw_strategy.runtime import StrategyRuntime


def _default_config_yaml() -> str:
    root = Path.home() / ".pnlclaw"
    data_dir = root / "data"
    lines = {
        "env": "development",
        "log_level": "INFO",
        "data_dir": str(data_dir).replace("\\", "/"),
        "db_path": str(DEFAULT_DB_PATH).replace("\\", "/"),
        "log_dir": str(root / "logs").replace("\\", "/"),
        "api_host": "127.0.0.1",
        "api_port": 8080,
        "default_exchange": "binance",
        "default_symbol": "BTCUSDT",
        "llm_provider": "openai_compatible",
        "llm_base_url": "",
        "llm_model": "",
        "llm_timeout_seconds": 60,
        "enable_real_trading": False,
        "paper_starting_balance": 10000.0,
    }
    result: str = yaml.safe_dump(lines, sort_keys=False, default_flow_style=False)
    return result


def _write_binance_key(key: str) -> None:
    d = Path.home() / ".pnlclaw" / "secrets" / "binance"
    d.mkdir(parents=True, exist_ok=True)
    key_file = d / "api_key"
    key_file.write_text(key.strip(), encoding="utf-8")
    try:
        key_file.chmod(0o600)
    except OSError:
        pass


def _demo_backtest() -> None:
    """Run a tiny SMA-style backtest using synthetic data (no fixture files required)."""
    n = 120
    start = pd.Timestamp("2024-01-01", tz="UTC")
    base = 40000 + (pd.Series(range(n)) * 10).values
    ts_ms = [int((start + pd.Timedelta(hours=i)).timestamp() * 1000) for i in range(n)]
    df = pd.DataFrame(
        {
            "timestamp": ts_ms,
            "open": base,
            "high": base * 1.001,
            "low": base * 0.999,
            "close": base,
            "volume": 1.0,
        }
    )
    with tempfile.TemporaryDirectory() as tmp:
        yml = Path(tmp) / "sma_demo.yaml"
        yml.write_text(
            """
id: demo-sma
name: Demo SMA
type: sma_cross
description: Setup wizard demo
symbols:
  - BTC/USDT
interval: 1h
parameters:
  sma_short: 10
  sma_long: 30
entry_rules: {}
exit_rules: {}
risk_params: {}
parsed_entry_rules:
  long:
    - indicator: sma
      params: {period: 10}
      operator: crosses_above
      comparator:
        indicator: sma
        params: {period: 30}
  short: []
parsed_exit_rules:
  close_long:
    - indicator: sma
      params: {period: 10}
      operator: crosses_below
      comparator:
        indicator: sma
        params: {period: 30}
  close_short: []
parsed_risk_params: {}
""".strip(),
            encoding="utf-8",
        )
        strat = load_strategy(yml)
        compiled = compile_strategy(strat)
        runtime = StrategyRuntime(compiled)
        engine = BacktestEngine(BacktestConfig(strategy_id=strat.id))
        result = engine.run(strategy=runtime, data=df)
        m = result.metrics
        click.echo(
            f"  Demo backtest finished: return={m.total_return:.2%}, "
            f"Sharpe={m.sharpe_ratio:.2f}, MDD={m.max_drawdown:.2%}, trades={result.trades_count}"
        )


@click.command("setup")
def setup() -> None:
    """Interactive first-time setup (all steps skippable)."""
    click.echo(f"PnLClaw Setup — CLI {cli_version()}")
    click.echo("=" * 40)

    # Step 1
    click.echo("\n[1/6] Environment")
    ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    click.echo(f"  Python {ver}")
    if sys.version_info < (3, 11):  # noqa: UP036
        click.echo("  Python 3.11+ is required. Please upgrade.")
        raise click.Abort()
    if not click.confirm("  Continue?", default=True):
        click.echo("Setup cancelled.")
        return

    # Step 2 — Exchange (optional)
    click.echo("\n[2/6] Exchange (Binance) — optional")
    if click.confirm("  Configure Binance API key now?", default=False):
        key = click.prompt("  API key", hide_input=True)
        if key.strip():
            _write_binance_key(key)
            click.echo("  Saved under ~/.pnlclaw/secrets/binance/api_key")

    # Step 3 — LLM
    click.echo("\n[3/6] LLM — optional")
    click.echo("  Provider: OpenAI-compatible / Ollama / Skip")
    choice = click.prompt(
        "  Choose [openai_compatible / ollama / skip]",
        default="skip",
        show_default=True,
    ).lower()
    llm_patch: dict = {}
    if choice in ("openai_compatible", "openai"):
        base = click.prompt("  Base URL (e.g. https://api.openai.com/v1)", default="")
        model = click.prompt("  Model name", default="")
        key = click.prompt("  API key", default="", hide_input=True)
        llm_patch = {
            "llm_provider": "openai_compatible",
            "llm_base_url": base,
            "llm_model": model,
        }
        if key.strip():
            os_environ_set = click.confirm(
                "  Store key in environment only (this session)?",
                default=False,
            )
            if os_environ_set:
                os.environ["OPENAI_API_KEY"] = key.strip()
                click.echo("  Set OPENAI_API_KEY for this process only.")
            else:
                sec = Path.home() / ".pnlclaw" / "secrets" / "openai" / "api_key"
                sec.parent.mkdir(parents=True, exist_ok=True)
                sec.write_text(key.strip(), encoding="utf-8")
                try:
                    sec.chmod(0o600)
                except OSError:
                    pass
                click.echo(f"  Wrote {sec}")
    elif choice == "ollama":
        base = click.prompt("  Ollama base URL", default="http://127.0.0.1:11434/v1")
        model = click.prompt("  Model name", default="llama3")
        llm_patch = {"llm_provider": "openai_compatible", "llm_base_url": base, "llm_model": model}

    # Step 4 — dirs + config + DB
    click.echo("\n[4/6] Data directory and database")
    root = Path.home() / ".pnlclaw"
    for sub in ("data", "logs", "paper", "secrets"):
        (root / sub).mkdir(parents=True, exist_ok=True)

    cfg_path = root / "config.yaml"
    if not cfg_path.exists():
        text = _default_config_yaml()
        if llm_patch:
            data = yaml.safe_load(text) or {}
            data.update(llm_patch)
            text = yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
        cfg_path.write_text(text, encoding="utf-8")
        sv_path = root / "schema_version"
        sv_path.write_text(SCHEMA_VERSION + "\n", encoding="utf-8")
        click.echo(f"  Wrote {cfg_path}")
    else:
        click.echo(f"  Config already exists: {cfg_path}")
        sv_path = root / "schema_version"
        if not sv_path.is_file():
            sv_path.write_text(SCHEMA_VERSION + "\n", encoding="utf-8")
        if llm_patch and click.confirm("  Merge LLM settings into existing config?", default=True):
            raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            raw.update(llm_patch)
            text = yaml.safe_dump(raw, sort_keys=False, default_flow_style=False)
            cfg_path.write_text(text, encoding="utf-8")

    async def _init_db() -> None:
        mgr = AsyncSQLiteManager(DEFAULT_DB_PATH)
        await mgr.connect()
        await mgr.close()

    asyncio.run(_init_db())
    click.echo(f"  SQLite ready at {DEFAULT_DB_PATH}")

    # Step 5 — demo
    click.echo("\n[5/6] Demo backtest (optional)")
    if click.confirm("  Run a quick SMA backtest on synthetic data?", default=False):
        try:
            _demo_backtest()
        except Exception as exc:
            click.echo(f"  Demo failed: {exc}")

    # Step 6
    click.echo("\n[6/6] Done")
    click.echo("  PnLClaw is ready. Try: pnlclaw status")
    click.echo("=" * 40)
