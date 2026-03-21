"""Singleton plugin registry: register/get/list plugins by capability type."""

from __future__ import annotations

import threading
from typing import Any


class PluginRegistry:
    """Singleton registry for all plugin capabilities.

    Plugins are stored by (capability_type, name). Supports register,
    get, and list operations.
    """

    _instance: PluginRegistry | None = None
    _lock = threading.Lock()

    def __new__(cls) -> PluginRegistry:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._plugins: dict[str, dict[str, Any]] = {}
                    cls._instance = inst
        return cls._instance

    def register(self, capability: str, name: str, instance: Any) -> None:
        """Register a plugin instance.

        Args:
            capability: Capability type (e.g. 'exchange', 'strategy', 'indicator').
            name: Unique name within the capability.
            instance: The plugin instance.

        Raises:
            ValueError: If a plugin with the same capability+name is already registered.
        """
        if capability not in self._plugins:
            self._plugins[capability] = {}
        if name in self._plugins[capability]:
            raise ValueError(f"Plugin '{name}' already registered for capability '{capability}'")
        self._plugins[capability][name] = instance

    def get(self, capability: str, name: str) -> Any:
        """Get a registered plugin by capability and name.

        Returns:
            The plugin instance, or None if not found.
        """
        return self._plugins.get(capability, {}).get(name)

    def list(self, capability: str) -> dict[str, Any]:
        """List all plugins for a given capability.

        Returns:
            Dict of {name: instance} for the capability.
        """
        return dict(self._plugins.get(capability, {}))

    def list_capabilities(self) -> list[str]:
        """List all registered capability types."""
        return list(self._plugins.keys())

    def clear(self) -> None:
        """Remove all registered plugins (useful for testing)."""
        self._plugins.clear()

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (for testing only)."""
        with cls._lock:
            cls._instance = None
