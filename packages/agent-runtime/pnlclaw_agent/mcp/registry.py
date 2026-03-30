"""McpRegistry -- manages all MCP server connections and tool registration.

Lifecycle:
    1. ``start(config, tool_catalog)`` -- connect to all configured servers,
       wrap their tools, and register them in the catalog.
    2. At runtime, servers can be added / removed / refreshed individually.
    3. ``stop()`` -- disconnect all servers and unregister their tools.
"""

from __future__ import annotations

import logging
from typing import Any

from pnlclaw_agent.mcp.client import McpClientError, McpClientSession
from pnlclaw_agent.mcp.tool_wrapper import McpToolWrapper
from pnlclaw_agent.mcp.types import (
    McpConfig,
    McpServerConfig,
    McpServerStatus,
    McpToolInfo,
)

logger = logging.getLogger(__name__)


class McpRegistry:
    """Manages all MCP server connections and their tool registrations.

    The registry sits between the MCP transport layer (``McpClientSession``)
    and the agent's ``ToolCatalog``.  It ensures that:

    * Each server's tools are namespaced to avoid collisions.
    * Disconnecting a server cleanly removes its tools from the catalog.
    * Tools from disabled servers are never registered.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, McpClientSession] = {}
        self._tools: dict[str, list[McpToolWrapper]] = {}  # server_name -> tools
        self._tool_catalog: Any | None = None  # ToolCatalog

    # -- bulk lifecycle ------------------------------------------------------

    async def start(self, config: McpConfig, tool_catalog: Any) -> None:
        """Connect to all configured MCP servers and register tools.

        Args:
            config: MCP configuration with server definitions.
            tool_catalog: ``ToolCatalog`` to register MCP tools into.
        """
        self._tool_catalog = tool_catalog
        reserved_names: set[str] = set(
            tool_catalog.tool_names() if hasattr(tool_catalog, "tool_names") else []
        )

        for server_name, server_config in config.servers.items():
            if not server_config.enabled:
                logger.info("MCP server '%s' is disabled, skipping", server_name)
                continue
            try:
                await self._connect_server(server_name, server_config, reserved_names)
            except Exception as exc:
                logger.warning("Failed to start MCP server '%s': %s", server_name, exc)

    async def stop(self) -> None:
        """Disconnect all MCP servers and unregister their tools."""
        for server_name in list(self._sessions.keys()):
            await self._disconnect_server(server_name)
        self._tool_catalog = None

    # -- individual server management ----------------------------------------

    async def add_server(self, name: str, config: McpServerConfig) -> McpServerStatus:
        """Add and connect a new MCP server at runtime.

        If a server with the same name already exists it is disconnected first.

        Args:
            name: Unique server name.
            config: Server configuration.

        Returns:
            Status of the newly added server.
        """
        if name in self._sessions:
            await self._disconnect_server(name)

        reserved_names: set[str] = set(
            self._tool_catalog.tool_names() if self._tool_catalog else []
        )
        try:
            await self._connect_server(name, config, reserved_names)
            return self._get_server_status(name)
        except Exception as exc:
            return McpServerStatus(name=name, config=config, connected=False, error=str(exc))

    async def remove_server(self, name: str) -> None:
        """Remove an MCP server and unregister its tools."""
        await self._disconnect_server(name)

    async def refresh_server(self, name: str) -> McpServerStatus:
        """Reconnect to a server and refresh its tools.

        Useful after a server process restart or tool list change.

        Args:
            name: Name of a previously added server.

        Returns:
            Updated server status.
        """
        if name not in self._sessions:
            return McpServerStatus(
                name=name,
                config=McpServerConfig(),
                connected=False,
                error=f"Server '{name}' not found",
            )

        session = self._sessions[name]
        config = session.config
        await self._disconnect_server(name)

        reserved_names: set[str] = set(
            self._tool_catalog.tool_names() if self._tool_catalog else []
        )
        try:
            await self._connect_server(name, config, reserved_names)
        except Exception as exc:
            logger.warning("Failed to refresh MCP server '%s': %s", name, exc)
        return self._get_server_status(name)

    # -- queries -------------------------------------------------------------

    def list_servers(self) -> list[McpServerStatus]:
        """List all MCP servers and their statuses."""
        return [self._get_server_status(name) for name in self._sessions]

    def list_mcp_tools(self) -> list[McpToolInfo]:
        """List all tools from all connected MCP servers."""
        tools: list[McpToolInfo] = []
        for server_tools in self._tools.values():
            for wrapper in server_tools:
                tools.append(wrapper._info)
        return tools

    # -- internal ------------------------------------------------------------

    async def _connect_server(
        self,
        name: str,
        config: McpServerConfig,
        reserved_names: set[str],
    ) -> None:
        """Connect to a single MCP server and register its tools."""
        session = McpClientSession(name, config)
        await session.connect()
        self._sessions[name] = session

        # Enumerate and wrap tools
        mcp_tools = await session.list_tools()
        wrappers: list[McpToolWrapper] = []

        for tool_info in mcp_tools:
            wrapper = McpToolWrapper(
                session=session,
                tool_info=tool_info,
                risk_level=config.risk_level,
            )
            if wrapper.name in reserved_names:
                logger.warning(
                    "MCP tool '%s' from server '%s' conflicts with existing tool, skipping",
                    wrapper.name,
                    name,
                )
                continue

            reserved_names.add(wrapper.name)
            wrappers.append(wrapper)

            # Register in ToolCatalog
            if self._tool_catalog is not None:
                try:
                    if hasattr(self._tool_catalog, "register_or_replace"):
                        self._tool_catalog.register_or_replace(wrapper)
                    else:
                        self._tool_catalog.register(wrapper)
                except Exception as exc:
                    logger.warning(
                        "Failed to register MCP tool '%s': %s", wrapper.name, exc
                    )

        self._tools[name] = wrappers
        logger.info(
            "MCP server '%s' connected with %d tools: %s",
            name,
            len(wrappers),
            ", ".join(w.name for w in wrappers),
        )

    async def _disconnect_server(self, name: str) -> None:
        """Disconnect a server and unregister its tools."""
        # Unregister tools first
        if name in self._tools and self._tool_catalog is not None:
            for wrapper in self._tools[name]:
                if hasattr(self._tool_catalog, "unregister"):
                    self._tool_catalog.unregister(wrapper.name)
            del self._tools[name]

        # Disconnect session
        if name in self._sessions:
            try:
                await self._sessions[name].disconnect()
            except Exception:
                logger.debug("Error disconnecting MCP server '%s'", name, exc_info=True)
            del self._sessions[name]

    def _get_server_status(self, name: str) -> McpServerStatus:
        """Build a status snapshot for a server."""
        session = self._sessions.get(name)
        if session is None:
            return McpServerStatus(
                name=name,
                config=McpServerConfig(),
                connected=False,
                error="Server not found",
            )
        tools = self._tools.get(name, [])
        return McpServerStatus(
            name=name,
            config=session.config,
            connected=session.connected,
            tool_count=len(tools),
            tools=[w._info for w in tools],
        )
