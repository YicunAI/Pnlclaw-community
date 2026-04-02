"""MCP client session -- manages connection to a single MCP server.

Uses the official ``mcp`` Python SDK for protocol handling.
Supports both stdio and SSE transports.

The ``mcp`` package is imported lazily so the rest of the module works
even when the SDK is not installed.
"""

from __future__ import annotations

import logging
from typing import Any

from pnlclaw_agent.mcp.types import McpServerConfig, McpToolInfo, McpToolResult, McpTransport

logger = logging.getLogger(__name__)


class McpClientError(Exception):
    """Raised when an MCP client operation fails."""


class McpClientSession:
    """Manages the connection to a single MCP server.

    Uses the official ``mcp`` Python SDK for protocol handling.
    Supports both stdio and SSE transports.

    Lifecycle:
        1. ``connect()``     -- establish transport and initialize session
        2. ``list_tools()``  -- enumerate available tools
        3. ``call_tool()``   -- invoke a tool
        4. ``disconnect()``  -- tear down transport and session
    """

    def __init__(self, server_name: str, config: McpServerConfig) -> None:
        self.server_name = server_name
        self.config = config
        self._session: Any | None = None  # mcp.ClientSession
        self._transport_ctx: Any | None = None  # async context manager for transport
        self._session_ctx: Any | None = None  # async context manager for session
        self._connected = False

    @property
    def connected(self) -> bool:
        """Whether the session is currently connected."""
        return self._connected

    # -- connection ----------------------------------------------------------

    async def connect(self) -> None:
        """Establish connection to the MCP server.

        Raises:
            McpClientError: If the ``mcp`` package is missing, the config is
                invalid, or the connection attempt fails.
        """
        # Lazy import of the mcp SDK
        try:
            from mcp import ClientSession  # noqa: F401
        except ImportError:
            raise McpClientError("The 'mcp' package is required for MCP support. Install it with: pip install mcp")

        errors = self.config.validate_config()
        if errors:
            raise McpClientError(f"Invalid MCP config for '{self.server_name}': {'; '.join(errors)}")

        try:
            if self.config.transport == McpTransport.STDIO:
                await self._connect_stdio()
            elif self.config.transport == McpTransport.SSE:
                await self._connect_sse()
            self._connected = True
            logger.info("MCP server '%s' connected successfully", self.server_name)
        except McpClientError:
            self._connected = False
            raise
        except Exception as exc:
            self._connected = False
            raise McpClientError(f"Failed to connect to MCP server '{self.server_name}': {exc}") from exc

    async def _connect_stdio(self) -> None:
        """Connect via stdio transport."""
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        assert self.config.command is not None

        server_params = StdioServerParameters(
            command=self.config.command,
            args=self.config.args,
            env={**self.config.env} if self.config.env else None,
            cwd=self.config.cwd,
        )

        # stdio_client is an async context manager yielding (read, write)
        self._transport_ctx = stdio_client(server_params)
        read_stream, write_stream = await self._transport_ctx.__aenter__()

        # Create and initialize the protocol session
        self._session_ctx = ClientSession(read_stream, write_stream)
        self._session = await self._session_ctx.__aenter__()
        await self._session.initialize()

    async def _connect_sse(self) -> None:
        """Connect via SSE transport."""
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        assert self.config.url is not None

        self._transport_ctx = sse_client(self.config.url)
        read_stream, write_stream = await self._transport_ctx.__aenter__()

        self._session_ctx = ClientSession(read_stream, write_stream)
        self._session = await self._session_ctx.__aenter__()
        await self._session.initialize()

    async def disconnect(self) -> None:
        """Disconnect from the MCP server and clean up resources.

        Safe to call even if already disconnected or never connected.
        Resources are closed in reverse order (session first, then transport).
        """
        self._connected = False

        # Close session first
        if self._session_ctx is not None:
            try:
                await self._session_ctx.__aexit__(None, None, None)
            except Exception:
                logger.debug("Error closing MCP session for '%s'", self.server_name, exc_info=True)
            self._session_ctx = None
            self._session = None

        # Then close transport
        if self._transport_ctx is not None:
            try:
                await self._transport_ctx.__aexit__(None, None, None)
            except Exception:
                logger.debug("Error closing MCP transport for '%s'", self.server_name, exc_info=True)
            self._transport_ctx = None

    # -- tool operations -----------------------------------------------------

    async def list_tools(self) -> list[McpToolInfo]:
        """Enumerate all tools from the MCP server.

        Returns:
            List of ``McpToolInfo`` describing each available tool.

        Raises:
            McpClientError: If not connected.
        """
        if not self._session:
            raise McpClientError(f"Not connected to MCP server '{self.server_name}'")

        result = await self._session.list_tools()
        tools: list[McpToolInfo] = []
        for tool in result.tools:
            tools.append(
                McpToolInfo(
                    server_name=self.server_name,
                    tool_name=tool.name,
                    description=tool.description or "",
                    input_schema=tool.inputSchema if isinstance(tool.inputSchema, dict) else {},
                )
            )
        return tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> McpToolResult:
        """Call a tool on the MCP server.

        Args:
            tool_name: Name of the tool (as returned by ``list_tools``).
            arguments: Tool arguments matching the tool's input schema.

        Returns:
            ``McpToolResult`` with text content and error flag.

        Raises:
            McpClientError: If not connected.
        """
        if not self._session:
            raise McpClientError(f"Not connected to MCP server '{self.server_name}'")

        try:
            result = await self._session.call_tool(tool_name, arguments)
        except Exception as exc:
            return McpToolResult(content=f"MCP tool call error: {exc}", is_error=True)

        # Extract text content from result items
        content_parts: list[str] = []
        if result.content:
            for item in result.content:
                if hasattr(item, "text"):
                    content_parts.append(item.text)
                elif hasattr(item, "data"):
                    mime = getattr(item, "mimeType", "unknown")
                    content_parts.append(f"[binary data: {mime}]")

        return McpToolResult(
            content="\n".join(content_parts) if content_parts else "",
            is_error=bool(result.isError),
        )

    # -- health --------------------------------------------------------------

    async def health_check(self) -> bool:
        """Check if the connection is healthy by issuing a lightweight request.

        Returns:
            ``True`` if the connection is alive, ``False`` otherwise.
        """
        if not self._connected or not self._session:
            return False
        try:
            await self._session.list_tools()
            return True
        except Exception:
            return False
