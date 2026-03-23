"""Plugin discovery: 4-tier priority chain with caching."""

from __future__ import annotations

import importlib.metadata
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredPlugin:
    """A discovered plugin with its source tier."""

    name: str
    module: str
    source: str  # "bundled" | "pip" | "workspace" | "user"
    metadata: dict[str, Any] = field(default_factory=dict)


class PluginDiscovery:
    """Four-tier plugin discovery with caching.

    Discovery priority (highest to lowest):
    1. **Bundled**: shipped with PnLClaw (hardcoded list)
    2. **Pip-installed**: discovered via ``importlib.metadata.entry_points``
    3. **Workspace**: found in a workspace plugins directory
    4. **User config**: declared in ``~/.pnlclaw/plugins.yaml``

    Results are cached after first discovery.
    """

    ENTRY_POINT_GROUP = "pnlclaw.plugins"

    def __init__(
        self,
        bundled: list[DiscoveredPlugin] | None = None,
        workspace_dir: Path | None = None,
        user_config_path: Path | None = None,
    ) -> None:
        self._bundled = bundled or []
        self._workspace_dir = workspace_dir
        self._user_config_path = user_config_path or (Path.home() / ".pnlclaw" / "plugins.yaml")
        self._cache: list[DiscoveredPlugin] | None = None

    def discover(self, *, force_refresh: bool = False) -> list[DiscoveredPlugin]:
        """Discover all plugins across all 4 tiers.

        Args:
            force_refresh: If True, ignore cache and re-discover.

        Returns:
            List of discovered plugins, deduplicated by name (first wins).
        """
        if self._cache is not None and not force_refresh:
            return list(self._cache)

        seen: set[str] = set()
        results: list[DiscoveredPlugin] = []

        # Tier 1: Bundled
        for p in self._bundled:
            if p.name not in seen:
                seen.add(p.name)
                results.append(p)

        # Tier 2: Pip entry_points
        for p in self._discover_pip():
            if p.name not in seen:
                seen.add(p.name)
                results.append(p)

        # Tier 3: Workspace
        for p in self._discover_workspace():
            if p.name not in seen:
                seen.add(p.name)
                results.append(p)

        # Tier 4: User config
        for p in self._discover_user_config():
            if p.name not in seen:
                seen.add(p.name)
                results.append(p)

        self._cache = results
        return list(results)

    def _discover_pip(self) -> list[DiscoveredPlugin]:
        """Discover plugins registered via pip entry_points."""
        found: list[DiscoveredPlugin] = []
        try:
            eps = importlib.metadata.entry_points()
            group: list[Any]
            if hasattr(eps, "select"):
                group = list(eps.select(group=self.ENTRY_POINT_GROUP))
            else:
                group = list(eps.get(self.ENTRY_POINT_GROUP, []))  # type: ignore[call-overload]
            for ep in group:
                found.append(
                    DiscoveredPlugin(
                        name=ep.name,
                        module=ep.value,
                        source="pip",
                    )
                )
        except Exception as exc:
            logger.debug("Failed to discover pip plugins: %s", exc)
        return found

    def _discover_workspace(self) -> list[DiscoveredPlugin]:
        """Discover plugins in the workspace directory."""
        if self._workspace_dir is None or not self._workspace_dir.is_dir():
            return []
        found: list[DiscoveredPlugin] = []
        for child in self._workspace_dir.iterdir():
            if child.is_dir() and (child / "__init__.py").is_file():
                found.append(
                    DiscoveredPlugin(
                        name=child.name,
                        module=str(child),
                        source="workspace",
                    )
                )
        return found

    def _discover_user_config(self) -> list[DiscoveredPlugin]:
        """Discover plugins declared in user config YAML."""
        if not self._user_config_path.is_file():
            return []
        try:
            import yaml  # type: ignore[import-untyped]

            with open(self._user_config_path) as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                return []
            plugins = data.get("plugins", [])
            return [
                DiscoveredPlugin(
                    name=p["name"],
                    module=p["module"],
                    source="user",
                )
                for p in plugins
                if isinstance(p, dict) and "name" in p and "module" in p
            ]
        except Exception as exc:
            logger.debug("Failed to read user plugins config: %s", exc)
            return []

    def invalidate_cache(self) -> None:
        """Clear the discovery cache."""
        self._cache = None
