"""Tests for KillSwitch (S2-H04)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pnlclaw_risk.kill_switch import KillSwitch


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    """Reset singleton before each test."""
    KillSwitch._reset_singleton()


@pytest.fixture
def state_path(tmp_path: Path) -> Path:
    return tmp_path / "kill_switch.json"


class TestKillSwitch:
    def test_default_inactive(self, state_path: Path) -> None:
        ks = KillSwitch(state_path)
        assert ks.is_active is False

    def test_activate(self, state_path: Path) -> None:
        ks = KillSwitch(state_path)
        ks.activate("test reason")
        assert ks.is_active is True
        assert ks.reason == "test reason"
        assert ks.activated_at is not None

    def test_deactivate(self, state_path: Path) -> None:
        ks = KillSwitch(state_path)
        ks.activate()
        ks.deactivate()
        assert ks.is_active is False
        assert ks.reason == ""

    def test_persists_across_instances(self, state_path: Path) -> None:
        ks1 = KillSwitch(state_path)
        ks1.activate("persist test")
        # Reset singleton to simulate restart
        KillSwitch._reset_singleton()

        ks2 = KillSwitch(state_path)
        assert ks2.is_active is True
        assert ks2.reason == "persist test"

    def test_status_dict(self, state_path: Path) -> None:
        ks = KillSwitch(state_path)
        ks.activate("status test")
        status = ks.status()
        assert status["active"] is True
        assert status["reason"] == "status test"
        assert status["activated_at"] is not None

    def test_corrupted_state_defaults_inactive(self, state_path: Path) -> None:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text("not valid json")
        ks = KillSwitch(state_path)
        assert ks.is_active is False

    def test_singleton_pattern(self, state_path: Path) -> None:
        ks1 = KillSwitch(state_path)
        ks2 = KillSwitch(state_path)
        assert ks1 is ks2
