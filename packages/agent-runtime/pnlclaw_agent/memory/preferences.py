"""User preferences — persistent preference storage for the agent.

Stores risk appetite, preferred symbols, timeframes, and strategy types.
Data is saved to ``~/.pnlclaw/memory/preferences.json``.

Source: distillation-plan-supplement-3, gap 18.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


_DEFAULT_PREFS_PATH = Path.home() / ".pnlclaw" / "memory" / "preferences.json"


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class RiskAppetite(str, Enum):
    """User risk preference level."""

    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class UserPreferences(BaseModel):
    """User trading preferences.

    Attributes:
        risk_appetite: Risk tolerance level.
        preferred_symbols: Frequently traded pairs.
        preferred_timeframes: Preferred chart intervals.
        preferred_strategy_types: Favoured strategy types.
    """

    risk_appetite: RiskAppetite = Field(
        RiskAppetite.MODERATE,
        description="User risk tolerance: conservative, moderate, or aggressive",
    )
    preferred_symbols: list[str] = Field(
        default_factory=list,
        description="Preferred trading pairs, e.g. ['BTC/USDT', 'ETH/USDT']",
    )
    preferred_timeframes: list[str] = Field(
        default_factory=list,
        description="Preferred kline intervals, e.g. ['1h', '4h', '1d']",
    )
    preferred_strategy_types: list[str] = Field(
        default_factory=list,
        description="Preferred strategy types, e.g. ['sma_cross', 'rsi_reversal']",
    )


# ---------------------------------------------------------------------------
# Persistence functions
# ---------------------------------------------------------------------------


def load_preferences(path: Path | None = None) -> UserPreferences:
    """Load user preferences from JSON file.

    Returns default preferences if the file does not exist.

    Args:
        path: Custom file path. Defaults to ``~/.pnlclaw/memory/preferences.json``.

    Returns:
        Loaded or default UserPreferences.
    """
    prefs_path = path or _DEFAULT_PREFS_PATH
    if not prefs_path.exists():
        return UserPreferences()

    try:
        data = json.loads(prefs_path.read_text(encoding="utf-8"))
        return UserPreferences.model_validate(data)
    except (json.JSONDecodeError, Exception):
        return UserPreferences()


def save_preferences(prefs: UserPreferences, path: Path | None = None) -> None:
    """Save user preferences to JSON file.

    Creates parent directories if needed.

    Args:
        prefs: Preferences to save.
        path: Custom file path.
    """
    prefs_path = path or _DEFAULT_PREFS_PATH
    prefs_path.parent.mkdir(parents=True, exist_ok=True)
    prefs_path.write_text(prefs.model_dump_json(indent=2), encoding="utf-8")


def update_preference(
    key: str,
    value: Any,
    path: Path | None = None,
) -> UserPreferences:
    """Update a single preference and save.

    Args:
        key: Preference field name (e.g. "risk_appetite").
        value: New value for the field.
        path: Custom file path.

    Returns:
        Updated UserPreferences.

    Raises:
        ValueError: If the key is not a valid preference field.
    """
    prefs = load_preferences(path)

    if not hasattr(prefs, key):
        valid_keys = list(UserPreferences.model_fields.keys())
        raise ValueError(f"Unknown preference '{key}'. Valid keys: {valid_keys}")

    setattr(prefs, key, value)
    save_preferences(prefs, path)
    return prefs
