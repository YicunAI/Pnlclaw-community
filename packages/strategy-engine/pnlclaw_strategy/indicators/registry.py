"""Indicator registry — register, retrieve, and list available indicators."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pnlclaw_strategy.indicators.base import Indicator


class IndicatorNotFoundError(Exception):
    """Raised when a requested indicator is not registered."""


class IndicatorRegistry:
    """Registry for technical indicator classes.

    Provides register/get/list operations. Built-in indicators (SMA, EMA,
    RSI, MACD) are registered by default when using the module-level
    ``indicator_registry`` instance.
    """

    def __init__(self) -> None:
        self._indicators: dict[str, type[Indicator]] = {}

    def register(self, name: str, indicator_cls: type[Indicator]) -> None:
        """Register an indicator class under the given name.

        Args:
            name: Lowercase identifier (e.g. ``"sma"``).
            indicator_cls: The indicator class (not an instance).
        """
        self._indicators[name.lower()] = indicator_cls

    def get(self, name: str) -> type[Indicator]:
        """Retrieve a registered indicator class by name.

        Args:
            name: Indicator name (case-insensitive).

        Returns:
            The indicator class.

        Raises:
            IndicatorNotFoundError: If the name is not registered.
        """
        key = name.lower()
        if key not in self._indicators:
            raise IndicatorNotFoundError(f"Indicator '{name}' not found. Available: {sorted(self._indicators.keys())}")
        return self._indicators[key]

    def list(self) -> list[str]:
        """Return sorted list of all registered indicator names."""
        return sorted(self._indicators.keys())

    def has(self, name: str) -> bool:
        """Check if an indicator is registered."""
        return name.lower() in self._indicators


def _create_default_registry() -> IndicatorRegistry:
    """Create a registry with the built-in indicators pre-registered."""
    from pnlclaw_strategy.indicators.bbands import BollingerBands
    from pnlclaw_strategy.indicators.ema import EMA
    from pnlclaw_strategy.indicators.macd import MACD
    from pnlclaw_strategy.indicators.rsi import RSI
    from pnlclaw_strategy.indicators.sma import SMA

    registry = IndicatorRegistry()
    registry.register("sma", SMA)
    registry.register("ema", EMA)
    registry.register("rsi", RSI)
    registry.register("macd", MACD)
    registry.register("bbands", BollingerBands)
    return registry


# Module-level singleton with built-in indicators
indicator_registry: IndicatorRegistry = _create_default_registry()
