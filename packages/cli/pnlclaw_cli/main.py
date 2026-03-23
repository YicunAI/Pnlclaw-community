"""PnLClaw CLI entrypoint (Click)."""

from __future__ import annotations

import os
import sys
import traceback

import click

from pnlclaw_cli.commands.backtest import backtest_group
from pnlclaw_cli.commands.doctor_cmd import doctor
from pnlclaw_cli.commands.market import market_group
from pnlclaw_cli.commands.paper import paper_group
from pnlclaw_cli.commands.setup import setup
from pnlclaw_cli.commands.status import status
from pnlclaw_cli.constants import cli_version


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """PnLClaw — local-first crypto quant research and paper trading."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


cli.add_command(setup)
cli.add_command(status)
cli.add_command(market_group, name="market")
cli.add_command(backtest_group, name="backtest")
cli.add_command(paper_group, name="paper")
cli.add_command(doctor)


@cli.command("version")
def version_cmd() -> None:
    """Show CLI version."""
    click.echo(f"PnLClaw v{cli_version()}")


def main() -> None:
    """Console script entry: catch errors and avoid tracebacks for users."""
    try:
        cli.main(standalone_mode=True)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        click.echo("\nInterrupted.", err=True)
        sys.exit(130)
    except click.ClickException as exc:
        click.echo(exc.format_message(), err=True)
        sys.exit(exc.exit_code)
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        if os.environ.get("PNLCLAW_DEBUG", "").lower() in ("1", "true", "yes"):
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
