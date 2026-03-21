"""Plugin loader: load plugin modules via importlib and validate with Pydantic."""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class PluginManifest(BaseModel):
    """Pydantic model for plugin manifest validation."""

    name: str
    version: str = "0.0.0"
    description: str = ""
    capabilities: list[str] = []
    entry_point: str = ""  # e.g. "my_plugin:setup"


@dataclass
class LoadedPlugin:
    """A successfully loaded plugin."""

    name: str
    module: Any
    manifest: PluginManifest
    setup_fn: Any | None = None


class PluginLoader:
    """Load plugins by importing their Python modules.

    Supports loading via:
    - Module path (e.g. 'pnlclaw_exchange_binance')
    - Entry point string (e.g. 'my_plugin:setup')

    Validates the plugin against ``PluginManifest`` if a ``MANIFEST``
    attribute is present on the module.
    """

    def load(self, module_path: str) -> LoadedPlugin:
        """Load a plugin from a Python module path.

        Args:
            module_path: Dotted Python import path (e.g. 'my_plugin').

        Returns:
            LoadedPlugin with module reference and validated manifest.

        Raises:
            ImportError: If the module cannot be imported.
            ValidationError: If the manifest is invalid.
        """
        module = importlib.import_module(module_path)

        # Extract manifest
        raw_manifest = getattr(module, "MANIFEST", None)
        if isinstance(raw_manifest, dict):
            manifest = PluginManifest(**raw_manifest)
        elif isinstance(raw_manifest, PluginManifest):
            manifest = raw_manifest
        else:
            manifest = PluginManifest(name=module_path)

        # Extract setup function
        setup_fn = getattr(module, "setup", None)

        return LoadedPlugin(
            name=manifest.name,
            module=module,
            manifest=manifest,
            setup_fn=setup_fn,
        )

    def load_entry_point(self, entry_point: str) -> LoadedPlugin:
        """Load a plugin from an entry point string like 'module:attr'.

        Args:
            entry_point: String in the form 'module_path:attr_name'.

        Returns:
            LoadedPlugin.
        """
        if ":" in entry_point:
            module_path, attr_name = entry_point.rsplit(":", 1)
        else:
            module_path = entry_point
            attr_name = "setup"

        module = importlib.import_module(module_path)
        setup_fn = getattr(module, attr_name, None)

        raw_manifest = getattr(module, "MANIFEST", None)
        if isinstance(raw_manifest, dict):
            manifest = PluginManifest(**raw_manifest)
        else:
            manifest = PluginManifest(name=module_path)

        return LoadedPlugin(
            name=manifest.name,
            module=module,
            manifest=manifest,
            setup_fn=setup_fn,
        )
