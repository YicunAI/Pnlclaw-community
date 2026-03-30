"""State persistence for paper trading.

Serializes accounts, orders, positions, and fills to JSON files under
~/.pnlclaw/paper/ using atomic_write for crash safety.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pnlclaw_core.infra.atomic_write import atomic_write
from pnlclaw_paper.accounts import AccountManager, PaperAccount
from pnlclaw_paper.orders import PaperOrderManager
from pnlclaw_paper.positions import PositionManager
from pnlclaw_types.trading import Fill

logger = logging.getLogger(__name__)

_DEFAULT_STATE_DIR = Path.home() / ".pnlclaw" / "paper"

_STATE_FILES = (
    "accounts.json", "orders.json", "positions.json", "fills.json", "meta.json",
)


class PaperState:
    """Manages persistence of paper trading state.

    Saves to / loads from JSON files under a configurable directory.
    Includes fills history and per-account fee configuration.

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
        fills: list[Fill] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Serialize all managers and fills to JSON files."""
        self._dir.mkdir(parents=True, exist_ok=True)

        accounts_data = {aid: acc.model_dump() for aid, acc in account_mgr.get_all_data().items()}
        atomic_write(
            self._dir / "accounts.json",
            json.dumps(accounts_data, indent=2),
        )

        atomic_write(
            self._dir / "orders.json",
            json.dumps(order_mgr.get_all_data(), indent=2),
        )

        atomic_write(
            self._dir / "positions.json",
            json.dumps(position_mgr.get_all_data(), indent=2),
        )

        if fills is not None:
            fills_data = [f.model_dump() for f in fills]
            atomic_write(
                self._dir / "fills.json",
                json.dumps(fills_data, indent=2),
            )

        if extra is not None:
            atomic_write(
                self._dir / "meta.json",
                json.dumps(extra, indent=2),
            )

        logger.debug("Paper state saved to %s", self._dir)

    def load_state(
        self,
        account_mgr: AccountManager,
        order_mgr: PaperOrderManager,
        position_mgr: PositionManager,
    ) -> tuple[list[Fill], dict[str, Any]]:
        """Load persisted state into managers.

        Returns (fills_list, extra_metadata_dict).
        """
        accounts_path = self._dir / "accounts.json"
        if accounts_path.exists():
            raw = accounts_path.read_text(encoding="utf-8")
            accounts_data = json.loads(raw)
            loaded = {aid: PaperAccount.model_validate(data) for aid, data in accounts_data.items()}
            account_mgr.load_data(loaded)
            logger.info("Loaded %d paper accounts from %s", len(loaded), accounts_path)

        orders_path = self._dir / "orders.json"
        if orders_path.exists():
            raw = orders_path.read_text(encoding="utf-8")
            order_mgr.load_data(json.loads(raw))

        positions_path = self._dir / "positions.json"
        if positions_path.exists():
            raw = positions_path.read_text(encoding="utf-8")
            position_mgr.load_data(json.loads(raw))

        fills: list[Fill] = []
        fills_path = self._dir / "fills.json"
        if fills_path.exists():
            raw = fills_path.read_text(encoding="utf-8")
            fills_data = json.loads(raw)
            fills = [Fill.model_validate(f) for f in fills_data]
            logger.info("Loaded %d fills from %s", len(fills), fills_path)

        meta: dict[str, Any] = {}
        meta_path = self._dir / "meta.json"
        if meta_path.exists():
            raw = meta_path.read_text(encoding="utf-8")
            loaded = json.loads(raw)
            meta = loaded if isinstance(loaded, dict) else {}

        return fills, meta

    def clear_state(self) -> None:
        """Remove all persisted state files."""
        for fname in _STATE_FILES:
            p = self._dir / fname
            if p.exists():
                p.unlink()
