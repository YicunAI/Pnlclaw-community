"""Component registry for PnLClaw Open Core architecture.

Community edition registers basic implementations at startup.
Pro edition can replace them at runtime via ``replace()``.

Extension points for community contributors:
- ExchangeSource (exchange data adapters)
- Indicator (technical indicators)
- Skills (knowledge skill packs)
- MCP (model context protocol servers)
- Tool Catalog (tool registration)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ComponentRegistry:
    """Component registry — Community registers basics, Pro injects via replace().

    Thread-safe singleton pattern. Components are identified by string names.
    """

    def __init__(self) -> None:
        self._components: dict[str, Any] = {}

    def register(self, name: str, implementation: Any) -> None:
        """Register a component implementation.

        Raises:
            KeyError: If a component with the same name is already registered.
        """
        if name in self._components:
            raise KeyError(
                f"Component '{name}' is already registered. Use replace() to override existing implementations."
            )
        self._components[name] = implementation
        logger.info("Registered component: %s (%s)", name, type(implementation).__name__)

    def get(self, name: str) -> Any:
        """Get a registered component by name.

        Raises:
            KeyError: If the component is not registered.
        """
        if name not in self._components:
            raise KeyError(
                f"Component '{name}' is not registered. "
                f"Available: {', '.join(sorted(self._components.keys())) or 'none'}"
            )
        return self._components[name]

    def replace(self, name: str, implementation: Any) -> None:
        """Replace an existing component implementation (Pro extension entry point).

        Raises:
            KeyError: If the component is not already registered.
        """
        if name not in self._components:
            raise KeyError(f"Cannot replace '{name}': not registered. Use register() first.")
        old_type = type(self._components[name]).__name__
        self._components[name] = implementation
        logger.info(
            "Replaced component: %s (%s → %s)",
            name,
            old_type,
            type(implementation).__name__,
        )

    def list_registered(self) -> dict[str, str]:
        """Return all registered component names mapped to implementation class names."""
        return {name: type(impl).__name__ for name, impl in sorted(self._components.items())}

    def is_registered(self, name: str) -> bool:
        """Check if a component is registered."""
        return name in self._components

    def __len__(self) -> int:
        return len(self._components)
