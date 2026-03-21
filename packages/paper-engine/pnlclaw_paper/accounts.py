"""Paper trading account management.

In-memory store with JSON file persistence. No database required.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum

from pydantic import BaseModel, Field


class AccountStatus(str, Enum):
    """Paper account lifecycle states."""

    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"


class PaperAccount(BaseModel):
    """A paper trading account with balance tracking."""

    id: str = Field(default_factory=lambda: f"pa-{uuid.uuid4().hex[:8]}")
    name: str = Field(..., min_length=1, description="Human-readable account name")
    initial_balance: float = Field(..., gt=0, description="Starting balance in quote currency")
    current_balance: float = Field(..., description="Current available balance")
    status: AccountStatus = Field(AccountStatus.ACTIVE, description="Account status")
    created_at: int = Field(
        default_factory=lambda: int(time.time() * 1000),
        description="Creation time (ms epoch)",
    )
    updated_at: int = Field(
        default_factory=lambda: int(time.time() * 1000),
        description="Last update time (ms epoch)",
    )


class AccountManager:
    """CRUD operations for paper trading accounts.

    Stores accounts in memory. Use state.py for JSON persistence.
    """

    def __init__(self) -> None:
        self._accounts: dict[str, PaperAccount] = {}

    def create_account(self, name: str, initial_balance: float) -> PaperAccount:
        """Create a new paper account."""
        account = PaperAccount(
            name=name,
            initial_balance=initial_balance,
            current_balance=initial_balance,
        )
        self._accounts[account.id] = account
        return account

    def get_account(self, account_id: str) -> PaperAccount | None:
        """Get an account by ID, or None if not found."""
        return self._accounts.get(account_id)

    def list_accounts(self) -> list[PaperAccount]:
        """List all accounts."""
        return list(self._accounts.values())

    def delete_account(self, account_id: str) -> bool:
        """Delete an account. Returns True if found and deleted."""
        return self._accounts.pop(account_id, None) is not None

    def reset_account(self, account_id: str) -> PaperAccount | None:
        """Reset an account to its initial balance and ACTIVE status."""
        account = self._accounts.get(account_id)
        if account is None:
            return None
        account.current_balance = account.initial_balance
        account.status = AccountStatus.ACTIVE
        account.updated_at = int(time.time() * 1000)
        return account

    def update_balance(self, account_id: str, delta: float) -> PaperAccount | None:
        """Adjust balance by delta (positive = credit, negative = debit)."""
        account = self._accounts.get(account_id)
        if account is None:
            return None
        account.current_balance += delta
        account.updated_at = int(time.time() * 1000)
        return account

    def set_status(self, account_id: str, status: AccountStatus) -> PaperAccount | None:
        """Update account status."""
        account = self._accounts.get(account_id)
        if account is None:
            return None
        account.status = status
        account.updated_at = int(time.time() * 1000)
        return account

    def get_all_data(self) -> dict[str, PaperAccount]:
        """Return internal accounts dict (for serialization)."""
        return dict(self._accounts)

    def load_data(self, accounts: dict[str, PaperAccount]) -> None:
        """Load accounts from deserialized data."""
        self._accounts = dict(accounts)
