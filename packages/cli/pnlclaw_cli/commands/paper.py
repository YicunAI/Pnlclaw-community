"""Paper trading CLI."""

from __future__ import annotations

import click

from pnlclaw_paper.accounts import AccountManager
from pnlclaw_paper.orders import PaperOrderManager
from pnlclaw_paper.pnl import calculate_account_pnl
from pnlclaw_paper.positions import PositionManager
from pnlclaw_paper.state import PaperState


def _load_managers() -> tuple[AccountManager, PaperOrderManager, PositionManager, PaperState]:
    state = PaperState()
    am: AccountManager = AccountManager()
    om: PaperOrderManager = PaperOrderManager()
    pm: PositionManager = PositionManager()
    state.load_state(am, om, pm)
    return am, om, pm, state


def _save(
    am: AccountManager,
    om: PaperOrderManager,
    pm: PositionManager,
    state: PaperState,
) -> None:
    state.save_state(am, om, pm)


@click.group("paper")
def paper_group() -> None:
    """Paper trading accounts (JSON state under ~/.pnlclaw/paper/)."""


@paper_group.command("create")
@click.option("--name", required=True, help="Paper account name.")
@click.option("--balance", default=10_000.0, show_default=True, type=float)
def paper_create(name: str, balance: float) -> None:
    """Create a paper account."""
    am, om, pm, state = _load_managers()
    acc = am.create_account(name, balance)
    _save(am, om, pm, state)
    click.echo(f"Created paper account {acc.id} ({acc.name}) balance={acc.initial_balance}")


@paper_group.command("list")
def paper_list() -> None:
    """List paper accounts."""
    am, _, _, _ = _load_managers()
    rows = am.list_accounts()
    if not rows:
        click.echo("No paper accounts.")
        return
    click.echo(f"{'ID':<14} {'Name':<20} {'Balance':>12} {'Status'}")
    for a in rows:
        click.echo(f"{a.id:<14} {a.name:<20} {a.current_balance:>12.2f} {a.status.value}")


@paper_group.command("positions")
@click.argument("account_id")
def paper_positions(account_id: str) -> None:
    """Show open positions for an account."""
    _, _, pm, _ = _load_managers()
    pos = pm.get_open_positions(account_id)
    if not pos:
        click.echo("No open positions.")
        return
    for p in pos:
        click.echo(
            f"{p.symbol}  qty={p.quantity:.6f}  side={p.side.value}  "
            f"avg={p.avg_entry_price:.4f}  uPnL={p.unrealized_pnl:.2f}"
        )


@paper_group.command("pnl")
@click.argument("account_id")
@click.option(
    "--price",
    "prices",
    multiple=True,
    type=(str, float),
    help="Mark price for a symbol (repeatable): --price BTC/USDT 65000",
)
def paper_pnl(account_id: str, prices: tuple[tuple[str, float], ...]) -> None:
    """Estimate PnL per position (pass --price for unrealized marks)."""
    am, _, pm, _ = _load_managers()
    if am.get_account(account_id) is None:
        raise click.ClickException(f"Unknown account: {account_id}")
    positions = pm.get_positions(account_id)
    if not positions:
        click.echo("No positions.")
        return
    price_map = {sym: float(px) for sym, px in prices}
    records = calculate_account_pnl(positions, price_map)
    total = 0.0
    for rec in records:
        click.echo(
            f"{rec.symbol}: realized={rec.realized_pnl:.2f} unrealized={rec.unrealized_pnl:.2f} "
            f"total={rec.total_pnl:.2f} fees={rec.fees:.2f}"
        )
        total += rec.total_pnl
    click.echo(f"Total PnL (approx): {total:.2f}")
