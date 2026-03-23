"""Tests for CLI main group and version."""

from __future__ import annotations

import pytest
from click.testing import CliRunner
from pnlclaw_cli.main import cli


def test_cli_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "setup" in result.output
    assert "doctor" in result.output


def test_version_subcommand() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["version"])
    assert result.exit_code == 0
    assert "PnLClaw v" in result.output


def test_main_handles_keyboard_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    import pnlclaw_cli.main as main_mod

    def boom(*_a: object, **_k: object) -> None:
        raise KeyboardInterrupt()

    monkeypatch.setattr(main_mod.cli, "main", boom)
    with pytest.raises(SystemExit) as ei:
        main_mod.main()
    assert ei.value.code == 130


def test_main_handles_generic_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import pnlclaw_cli.main as main_mod

    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("x")

    monkeypatch.setattr(main_mod.cli, "main", boom)
    with pytest.raises(SystemExit) as ei:
        main_mod.main()
    assert ei.value.code == 1
