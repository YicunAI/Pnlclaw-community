"""`pnlclaw status` — quick environment summary."""

from __future__ import annotations

import os
from pathlib import Path

import click
import httpx

from pnlclaw_cli.constants import cli_version
from pnlclaw_core.config import load_config


def _tilde_path(p: Path) -> str:
    home = Path.home()
    try:
        rel = p.relative_to(home)
        return "~/" + str(rel).replace("\\", "/")
    except ValueError:
        return str(p)


def _exchange_line() -> str:
    if os.environ.get("BINANCE_API_KEY") or os.environ.get("PNLCLAW_BINANCE_API_KEY"):
        return "Configured"
    key_file = Path.home() / ".pnlclaw" / "secrets" / "binance" / "api_key"
    if key_file.is_file():
        return "Configured"
    return "Not configured"


def _llm_line(cfg) -> str:
    if os.environ.get("OPENAI_API_KEY") or os.environ.get("PNLCLAW_LLM_API_KEY"):
        return "Configured"
    if (cfg.llm_base_url or "").strip():
        return "Configured"
    return "Not configured"


def _api_status(port: int) -> str:
    url = f"http://127.0.0.1:{port}/api/v1/health"
    try:
        with httpx.Client(timeout=2.0) as client:
            r = client.get(url)
            if r.status_code == 200:
                return "Running"
    except httpx.HTTPError:
        pass
    return "Stopped"


@click.command("status")
def status() -> None:
    """Show PnLClaw environment status."""
    cfg = load_config()
    config_path = Path.home() / ".pnlclaw" / "config.yaml"
    db_path = Path(cfg.db_path)
    if not db_path.is_absolute():
        db_path = Path(cfg.db_path).resolve()

    cfg_ok = "OK" if config_path.is_file() else "Missing"
    db_ok = "OK" if db_path.is_file() else "Missing"

    click.echo(f"PnLClaw v{cli_version()}")
    click.echo("─────────────────────────────")
    click.echo(f"Config:     {_tilde_path(config_path)} [{cfg_ok}]")
    click.echo(f"Database:   {_tilde_path(db_path)} [{db_ok}]")
    click.echo(f"Exchange:   {_exchange_line()}")
    click.echo(f"LLM:        {_llm_line(cfg)}")
    port = cfg.api_port
    api_state = _api_status(port)
    click.echo(f"API Server: http://localhost:{port} [{api_state}]")
