"""Tests for setup wizard helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner
from pnlclaw_cli.commands.setup import _default_config_yaml, _write_binance_key


def test_default_config_yaml_is_valid() -> None:
    raw = yaml.safe_load(_default_config_yaml())
    assert raw["api_port"] == 8080


def test_write_binance_key_creates_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "h"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    _write_binance_key("secret-key")
    p = home / ".pnlclaw" / "secrets" / "binance" / "api_key"
    assert p.read_text() == "secret-key"


def test_setup_aborts_when_python_too_old(monkeypatch: pytest.MonkeyPatch) -> None:
    from pnlclaw_cli.commands import setup as setup_mod

    monkeypatch.setattr(setup_mod.sys, "version_info", (3, 10, 0))
    runner = CliRunner()
    result = runner.invoke(setup_mod.setup, [])
    assert result.exit_code != 0


def test_setup_minimal_invocation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Drive setup with defaults; mock asyncio DB init."""
    from pnlclaw_cli.commands import setup as setup_mod

    monkeypatch.setattr(setup_mod.sys, "version_info", sys.version_info)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    dbp = tmp_path / ".pnlclaw" / "data" / "pnlclaw.db"
    monkeypatch.setattr(setup_mod, "DEFAULT_DB_PATH", dbp)

    runner = CliRunner()
    result = runner.invoke(
        setup_mod.setup,
        input="\n\n\n\n",
    )
    assert result.exit_code == 0
    assert (tmp_path / ".pnlclaw" / "config.yaml").is_file()
    assert dbp.is_file()
