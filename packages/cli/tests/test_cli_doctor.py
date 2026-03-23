"""Tests for doctor command and checks."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner
from pnlclaw_cli.commands.doctor_cmd import doctor
from pnlclaw_cli.doctor.checks import ALL_CHECKS, CheckResult, check_python_version
from pnlclaw_cli.doctor.runner import print_report, run_all_checks


def test_nineteen_checks_registered() -> None:
    assert len(ALL_CHECKS) == 19


def test_check_python_version_returns_result() -> None:
    r = check_python_version()
    assert isinstance(r, CheckResult)
    assert r.status == "pass"


def test_run_all_checks_runs() -> None:
    results = run_all_checks()
    assert len(results) == 19


def test_print_report_smoke(capsys) -> None:
    results = run_all_checks()
    print_report(results)
    out = capsys.readouterr().out
    assert "PnLClaw Doctor" in out
    assert "Result:" in out


def test_doctor_cli() -> None:
    runner = CliRunner()
    result = runner.invoke(doctor, [])
    assert result.exit_code == 0
    assert "PnLClaw Doctor" in result.output


def test_doctor_repair_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    from pnlclaw_cli.commands import doctor_cmd as dc

    runner = CliRunner()
    result = runner.invoke(dc.doctor, ["--repair"])
    assert result.exit_code == 0
    assert "Repair:" in result.output
