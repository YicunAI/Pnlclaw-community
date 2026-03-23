"""Market data via local API REST."""

from __future__ import annotations

import json

import click
import httpx

from pnlclaw_core.config import load_config


def _api_base() -> str:
    cfg = load_config()
    host = "127.0.0.1" if cfg.api_host in ("0.0.0.0", "::") else cfg.api_host
    return f"http://{host}:{cfg.api_port}"


def _norm_symbol(symbol: str) -> str:
    return symbol.replace("/", "-").upper()


@click.group("market")
def market_group() -> None:
    """Fetch ticker / kline from the local API."""


@market_group.command("ticker")
@click.argument("symbol")
def market_ticker(symbol: str) -> None:
    """Latest ticker for SYMBOL (e.g. BTC-USDT or BTC/USDT)."""
    sym = _norm_symbol(symbol)
    url = f"{_api_base()}/api/v1/markets/{sym}/ticker"
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(url)
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPError as exc:
        raise click.ClickException(f"Could not fetch ticker: {exc}") from exc
    click.echo(json.dumps(body, indent=2))


@market_group.command("kline")
@click.argument("symbol")
@click.option("--interval", default="1h", show_default=True, help="Kline interval label.")
@click.option("--limit", default=100, show_default=True, type=int)
def market_kline(symbol: str, interval: str, limit: int) -> None:
    """Latest cached kline(s) for SYMBOL."""
    sym = _norm_symbol(symbol)
    url = f"{_api_base()}/api/v1/markets/{sym}/kline"
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(url, params={"interval": interval, "limit": limit})
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPError as exc:
        raise click.ClickException(f"Could not fetch kline: {exc}") from exc
    click.echo(json.dumps(body, indent=2))
