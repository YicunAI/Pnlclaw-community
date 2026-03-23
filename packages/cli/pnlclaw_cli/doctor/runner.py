"""Run doctor checks and format output."""

from __future__ import annotations

from pnlclaw_cli.ansi import RESET, dim, err, ok, warn
from pnlclaw_cli.constants import cli_version
from pnlclaw_cli.doctor.checks import ALL_CHECKS, CheckResult


def _glyph(st: str) -> str:
    if st == "pass":
        return ok("✓")
    if st == "fail":
        return err("✗")
    if st == "warn":
        return warn("!")
    return dim("─")


def run_all_checks() -> list[CheckResult]:
    results: list[CheckResult] = []
    for fn in ALL_CHECKS:
        results.append(fn())
    return results


def print_report(results: list[CheckResult]) -> None:
    title = f"PnLClaw Doctor v{cli_version()}"
    line = "═" * max(38, len(title))
    print(title)
    print(line)
    col = 28
    for r in results:
        name_padded = f"{r.name:<{col}}"
        print(f"{_glyph(r.status)} {name_padded} {r.message}{RESET}")
    print(line)
    passed = sum(1 for r in results if r.status == "pass")
    failed = sum(1 for r in results if r.status == "fail")
    warnings = sum(1 for r in results if r.status == "warn")
    skipped = sum(1 for r in results if r.status == "skip")
    print(
        f"Result: {passed} passed, {failed} failed, {warnings} warning(s), {skipped} skipped",
    )
