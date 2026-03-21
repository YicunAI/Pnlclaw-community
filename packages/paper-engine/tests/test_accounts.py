"""Tests for PaperAccount and AccountManager (S2-G01)."""

from __future__ import annotations

import pytest

from pnlclaw_paper.accounts import AccountManager, AccountStatus, PaperAccount


class TestPaperAccount:
    def test_create_with_defaults(self) -> None:
        acc = PaperAccount(name="Test", initial_balance=10000, current_balance=10000)
        assert acc.name == "Test"
        assert acc.status == AccountStatus.ACTIVE
        assert acc.id.startswith("pa-")

    def test_balance_fields(self) -> None:
        acc = PaperAccount(name="X", initial_balance=5000, current_balance=4500)
        assert acc.initial_balance == 5000
        assert acc.current_balance == 4500


class TestAccountManager:
    def test_create_account(self) -> None:
        mgr = AccountManager()
        acc = mgr.create_account("Demo", 10000.0)
        assert acc.name == "Demo"
        assert acc.initial_balance == 10000.0
        assert acc.current_balance == 10000.0

    def test_get_account(self) -> None:
        mgr = AccountManager()
        acc = mgr.create_account("Demo", 10000.0)
        found = mgr.get_account(acc.id)
        assert found is not None
        assert found.id == acc.id

    def test_get_account_not_found(self) -> None:
        mgr = AccountManager()
        assert mgr.get_account("nonexistent") is None

    def test_list_accounts(self) -> None:
        mgr = AccountManager()
        mgr.create_account("A", 1000)
        mgr.create_account("B", 2000)
        assert len(mgr.list_accounts()) == 2

    def test_delete_account(self) -> None:
        mgr = AccountManager()
        acc = mgr.create_account("Del", 1000)
        assert mgr.delete_account(acc.id) is True
        assert mgr.get_account(acc.id) is None
        assert mgr.delete_account(acc.id) is False

    def test_reset_account(self) -> None:
        mgr = AccountManager()
        acc = mgr.create_account("Reset", 10000)
        mgr.update_balance(acc.id, -3000)
        mgr.set_status(acc.id, AccountStatus.PAUSED)
        reset = mgr.reset_account(acc.id)
        assert reset is not None
        assert reset.current_balance == 10000
        assert reset.status == AccountStatus.ACTIVE

    def test_update_balance(self) -> None:
        mgr = AccountManager()
        acc = mgr.create_account("Bal", 10000)
        mgr.update_balance(acc.id, -1500)
        assert mgr.get_account(acc.id).current_balance == 8500

    def test_set_status(self) -> None:
        mgr = AccountManager()
        acc = mgr.create_account("Status", 10000)
        mgr.set_status(acc.id, AccountStatus.STOPPED)
        assert mgr.get_account(acc.id).status == AccountStatus.STOPPED
