"""Tests for PaperState persistence including fills."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from pnlclaw_paper.accounts import AccountManager
from pnlclaw_paper.orders import PaperOrderManager
from pnlclaw_paper.positions import PositionManager
from pnlclaw_paper.state import PaperState
from pnlclaw_types.trading import Fill


def _make_fill(
    price: float = 67000.0,
    quantity: float = 10000.0,
    order_id: str = "ord-1",
    **kwargs,
) -> Fill:
    defaults = dict(
        id=f"fill-{int(time.time() * 1000)}",
        order_id=order_id,
        price=price,
        quantity=quantity,
        fee=quantity * 0.0005,
        fee_currency="USDT",
        fee_rate=0.0005,
        realized_pnl=0.0,
        exec_type="taker",
        side="buy",
        pos_side="long",
        symbol="BTC-USDT-SWAP",
        leverage=10,
        reduce_only=False,
        timestamp=int(time.time() * 1000),
    )
    defaults.update(kwargs)
    return Fill(**defaults)


class TestStatePersistence:
    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        state = PaperState(state_dir=tmp_path)
        acct_mgr = AccountManager()
        order_mgr = PaperOrderManager()
        pos_mgr = PositionManager()

        acct = acct_mgr.create_account("Test", 50000.0, maker_fee_rate=0.0001, taker_fee_rate=0.0003)
        acct.total_realized_pnl = 123.45
        acct.total_fee = 10.0

        fills = [_make_fill(), _make_fill(price=68000.0, side="sell", reduce_only=True)]

        state.save_state(acct_mgr, order_mgr, pos_mgr, fills=fills)

        assert (tmp_path / "accounts.json").exists()
        assert (tmp_path / "fills.json").exists()

        acct_mgr2 = AccountManager()
        order_mgr2 = PaperOrderManager()
        pos_mgr2 = PositionManager()

        loaded_fills, meta = state.load_state(acct_mgr2, order_mgr2, pos_mgr2)

        loaded_accts = acct_mgr2.list_accounts()
        assert len(loaded_accts) == 1
        assert loaded_accts[0].total_realized_pnl == pytest.approx(123.45)
        assert loaded_accts[0].total_fee == pytest.approx(10.0)
        assert loaded_accts[0].maker_fee_rate == pytest.approx(0.0001)
        assert loaded_accts[0].taker_fee_rate == pytest.approx(0.0003)

        assert len(loaded_fills) == 2
        assert loaded_fills[0].fee_rate == pytest.approx(0.0005)
        assert loaded_fills[1].reduce_only is True

    def test_clear_state(self, tmp_path: Path) -> None:
        state = PaperState(state_dir=tmp_path)
        acct_mgr = AccountManager()
        order_mgr = PaperOrderManager()
        pos_mgr = PositionManager()

        acct_mgr.create_account("Test", 10000.0)
        state.save_state(acct_mgr, order_mgr, pos_mgr, fills=[_make_fill()])

        assert (tmp_path / "accounts.json").exists()
        assert (tmp_path / "fills.json").exists()

        state.clear_state()

        assert not (tmp_path / "accounts.json").exists()
        assert not (tmp_path / "fills.json").exists()

    def test_load_empty_dir(self, tmp_path: Path) -> None:
        state = PaperState(state_dir=tmp_path)
        acct_mgr = AccountManager()
        order_mgr = PaperOrderManager()
        pos_mgr = PositionManager()

        fills, meta = state.load_state(acct_mgr, order_mgr, pos_mgr)
        assert fills == []
        assert meta == {}

    def test_fills_with_enriched_fields(self, tmp_path: Path) -> None:
        state = PaperState(state_dir=tmp_path)
        acct_mgr = AccountManager()
        order_mgr = PaperOrderManager()
        pos_mgr = PositionManager()

        fill = _make_fill(
            realized_pnl=500.0,
            exec_type="maker",
            fee_rate=0.0002,
            leverage=20,
        )
        state.save_state(acct_mgr, order_mgr, pos_mgr, fills=[fill])

        acct_mgr2 = AccountManager()
        order_mgr2 = PaperOrderManager()
        pos_mgr2 = PositionManager()
        loaded_fills, _ = state.load_state(acct_mgr2, order_mgr2, pos_mgr2)

        assert len(loaded_fills) == 1
        f = loaded_fills[0]
        assert f.realized_pnl == pytest.approx(500.0)
        assert f.exec_type == "maker"
        assert f.fee_rate == pytest.approx(0.0002)
        assert f.leverage == 20
