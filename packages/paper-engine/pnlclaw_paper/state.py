"""State persistence for paper trading.

Serializes accounts, orders, and positions to JSON files under
~/.pnlclaw/paper/ using atomic_write for crash safety.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pnlclaw_core.infra.atomic_write import atomic_write
from pnlclaw_paper.accounts import AccountManager, PaperAccount
from pnlclaw_paper.orders import PaperOrderManager
from pnlclaw_paper.positions import PositionManager

_DEFAULT_STATE_DIR = Path.home() / ".pnlclaw" / "paper"


class PaperState:
    """Manages persistence of paper trading state.

    Saves to / loads from JSON files under a configurable directory.

    Args:
        state_dir: Directory for state files. Defaults to ~/.pnlclaw/paper/.
    """

    def __init__(self, state_dir: Path | None = None) -> None:
        self._dir = state_dir or _DEFAULT_STATE_DIR

    @property
    def state_dir(self) -> Path:
        return self._dir

    def save_state(
        self,
        account_mgr: AccountManager,
        order_mgr: PaperOrderManager,
        position_mgr: PositionManager,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Serialize all managers to JSON files.

        Args:
            account_mgr: Account manager instance.
            order_mgr: Order manager instance.
            position_mgr: Position manager instance.
            extra: Additional metadata to persist (e.g., fee accumulators).
        """
        # Accounts
        accounts_data = {
            aid: acc.model_dump()
            for aid, acc in account_mgr.get_all_data().items()
        }
        atomic_write(
            self._dir / "accounts.json",
            json.dumps(accounts_data, indent=2),
        )

        # Orders
        atomic_write(
            self._dir / "orders.json",
            json.dumps(order_mgr.get_all_data(), indent=2),
        )

        # Positions
        atomic_write(
            self._dir / "positions.json",
            json.dumps(position_mgr.get_all_data(), indent=2),
        )

        # Extra metadata
        if extra is not None:
            atomic_write(
                self._dir / "meta.json",
                json.dumps(extra, indent=2),
            )

    def load_state(
        self,
        account_mgr: AccountManager,
        order_mgr: PaperOrderManager,
        position_mgr: PositionManager,
    ) -> dict[str, Any]:
        """Load persisted state into managers.

        Returns extra metadata dict (or empty dict if not found).
        """
        # Accounts
        accounts_path = self._dir / "accounts.json"
        if accounts_path.exists():
            raw = accounts_path.read_text(encoding="utf-8")
            accounts_data = json.loads(raw)
            loaded = {
                aid: PaperAccount.model_validate(data)
                for aid, data in accounts_data.items()
            }
            account_mgr.load_data(loaded)

        # Orders
        orders_path = self._dir / "orders.json"
        if orders_path.exists():
            raw = orders_path.read_text(encoding="utf-8")
            order_mgr.load_data(json.loads(raw))

        # Positions
        positions_path = self._dir / "positions.json"
        if positions_path.exists():
            raw = positions_path.read_text(encoding="utf-8")
            position_mgr.load_data(json.loads(raw))

        # Extra metadata
        meta_path = self._dir / "meta.json"
        if meta_path.exists():
            raw = meta_path.read_text(encoding="utf-8")
            loaded = json.loads(raw)
            return loaded if isinstance(loaded, dict) else {}

        return {}

    def clear_state(self) -> None:
        """Remove all persisted state files."""
        for fname in ("accounts.json", "orders.json", "positions.json", "meta.json"):
            p = self._dir / fname
            if p.exists():
                p.unlink()
