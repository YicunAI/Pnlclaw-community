"""Tests for state persistence (S2-G06)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pnlclaw_types.trading import OrderSide, OrderType

from pnlclaw_paper.accounts import AccountManager
from pnlclaw_paper.orders import PaperOrderManager
from pnlclaw_paper.positions import PositionManager
from pnlclaw_paper.state import PaperState


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    return tmp_path / "paper"


class TestPaperState:
    def test_save_and_load_accounts(self, state_dir: Path) -> None:
        ps = PaperState(state_dir)
        mgr = AccountManager()
        mgr.create_account("Test", 10000.0)

        ps.save_state(mgr, PaperOrderManager(), PositionManager())

        mgr2 = AccountManager()
        ps.load_state(mgr2, PaperOrderManager(), PositionManager())
        assert len(mgr2.list_accounts()) == 1
        assert mgr2.list_accounts()[0].name == "Test"

    def test_save_and_load_orders(self, state_dir: Path) -> None:
        ps = PaperState(state_dir)
        omgr = PaperOrderManager()
        omgr.place_order(
            "acc-1", symbol="BTC/USDT", side=OrderSide.BUY,
            order_type=OrderType.MARKET, quantity=0.5,
        )

        ps.save_state(AccountManager(), omgr, PositionManager())

        omgr2 = PaperOrderManager()
        ps.load_state(AccountManager(), omgr2, PositionManager())
        assert len(omgr2.get_orders("acc-1")) == 1

    def test_save_and_load_extra(self, state_dir: Path) -> None:
        ps = PaperState(state_dir)
        ps.save_state(
            AccountManager(), PaperOrderManager(), PositionManager(),
            extra={"fees": {"BTC/USDT": 42.5}},
        )

        extra = ps.load_state(AccountManager(), PaperOrderManager(), PositionManager())
        assert extra["fees"]["BTC/USDT"] == 42.5

    def test_load_empty_dir(self, state_dir: Path) -> None:
        ps = PaperState(state_dir)
        extra = ps.load_state(AccountManager(), PaperOrderManager(), PositionManager())
        assert extra == {}

    def test_clear_state(self, state_dir: Path) -> None:
        ps = PaperState(state_dir)
        mgr = AccountManager()
        mgr.create_account("Test", 10000.0)
        ps.save_state(mgr, PaperOrderManager(), PositionManager())

        ps.clear_state()
        assert not (state_dir / "accounts.json").exists()
