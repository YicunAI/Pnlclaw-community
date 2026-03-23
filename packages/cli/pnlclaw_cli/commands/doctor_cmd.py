"""`pnlclaw doctor` command."""

from __future__ import annotations

from pathlib import Path

import click

from pnlclaw_cli.doctor import repair as repair_mod
from pnlclaw_cli.doctor.runner import print_report, run_all_checks


@click.command("doctor")
@click.option(
    "--repair",
    "do_repair",
    is_flag=True,
    help="Create missing dirs, default config, initialize DB, fix permissions.",
)
def doctor(do_repair: bool) -> None:
    """Run environment diagnostics (19 checks)."""
    if do_repair:
        try:
            actions = repair_mod.run_standard_repairs()
            for a in actions:
                click.echo(f"Repair: {a}")
            repair_mod.chmod_user_only_path(Path.home() / ".pnlclaw")
            repair_mod.chmod_secret_files()
            click.echo("Repair: Tightened permissions where possible")
        except Exception as exc:
            raise click.ClickException(f"Repair failed: {exc}") from exc
    results = run_all_checks()
    print_report(results)
