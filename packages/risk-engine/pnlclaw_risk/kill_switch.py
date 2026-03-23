"""Emergency kill switch — singleton that blocks all new orders when active.

State is persisted to disk so it survives restarts.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from pnlclaw_core.infra.atomic_write import atomic_write

_DEFAULT_STATE_PATH = Path.home() / ".pnlclaw" / "kill_switch.json"


class KillSwitch:
    """Global emergency stop — blocks all new orders when active.

    Thread-safe singleton with persistent state.

    Args:
        state_path: Path for persisted state. Defaults to ~/.pnlclaw/kill_switch.json.
    """

    _instance: KillSwitch | None = None
    _lock = threading.Lock()

    def __new__(cls, state_path: Path | None = None) -> KillSwitch:
        with cls._lock:
            if cls._instance is None:
                instance = super().__new__(cls)
                instance._init(state_path or _DEFAULT_STATE_PATH)
                cls._instance = instance
            return cls._instance

    def _init(self, state_path: Path) -> None:
        self._state_path = state_path
        self._active = False
        self._activated_at: float | None = None
        self._reason: str = ""
        self._data_lock = threading.Lock()
        self._load()

    def activate(self, reason: str = "Manual activation") -> None:
        """Activate the kill switch — all new orders will be rejected."""
        with self._data_lock:
            self._active = True
            self._activated_at = time.time()
            self._reason = reason
            self._save()

    def deactivate(self) -> None:
        """Deactivate the kill switch — resume normal operations."""
        with self._data_lock:
            self._active = False
            self._activated_at = None
            self._reason = ""
            self._save()

    @property
    def is_active(self) -> bool:
        """Whether the kill switch is currently engaged."""
        with self._data_lock:
            return self._active

    @property
    def activated_at(self) -> float | None:
        """Epoch timestamp when activated, or None."""
        with self._data_lock:
            return self._activated_at

    @property
    def reason(self) -> str:
        """Reason for activation."""
        with self._data_lock:
            return self._reason

    def status(self) -> dict[str, object]:
        """Return kill switch status as a dict."""
        with self._data_lock:
            return {
                "active": self._active,
                "activated_at": self._activated_at,
                "reason": self._reason,
            }

    # -- persistence -----------------------------------------------------------

    def _save(self) -> None:
        """Persist state to disk using atomic write."""
        data = json.dumps(
            {
                "active": self._active,
                "activated_at": self._activated_at,
                "reason": self._reason,
            },
            indent=2,
        )
        atomic_write(self._state_path, data)

    def _load(self) -> None:
        """Load persisted state from disk."""
        if not self._state_path.exists():
            return
        try:
            raw = self._state_path.read_text(encoding="utf-8")
            state = json.loads(raw)
            self._active = bool(state.get("active", False))
            self._activated_at = state.get("activated_at")
            self._reason = str(state.get("reason", ""))
        except (json.JSONDecodeError, OSError):
            # Corrupted state — default to inactive (safe)
            self._active = False

    @classmethod
    def _reset_singleton(cls) -> None:
        """Reset singleton for testing. Not for production use."""
        with cls._lock:
            cls._instance = None
