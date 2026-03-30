"""McpToolWrapper -- adapts MCP tools to PnLClaw's BaseTool interface.

Each MCP tool discovered from a server is wrapped as a ``BaseTool`` subclass
so it can be registered in ``ToolCatalog`` and exposed to the LLM alongside
built-in tools.

Tool name format: ``mcp_{server}_{tool}`` (avoids collisions with built-in
tools).
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from pnlclaw_agent.mcp.types import McpToolInfo, McpToolResult
from pnlclaw_agent.tools.base import BaseTool, ToolResult
from pnlclaw_types.risk import RiskLevel


def _sanitize_name(s: str) -> str:
    """Sanitize a string for use in tool names (alphanumeric + underscore only)."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", s).strip("_").lower()


class McpToolWrapper(BaseTool):
    """Wraps an MCP server tool as a PnLClaw ``BaseTool``.

    The wrapper delegates ``execute()`` to the MCP client session, bridging
    the sync ``BaseTool`` interface with the async MCP SDK.

    Args:
        session: ``McpClientSession`` that owns the connection.
        tool_info: Metadata for the tool (name, schema, description).
        risk_level: Risk classification inherited from the server config.
    """

    def __init__(
        self,
        session: Any,  # McpClientSession (typed as Any to avoid circular import)
        tool_info: McpToolInfo,
        risk_level: RiskLevel = RiskLevel.RESTRICTED,
    ) -> None:
        self._session = session
        self._info = tool_info
        self._risk_level = risk_level

    @property
    def name(self) -> str:
        """Canonical tool name: ``mcp_{server}_{tool}``."""
        server = _sanitize_name(self._info.server_name)
        tool = _sanitize_name(self._info.tool_name)
        return f"mcp_{server}_{tool}"

    @property
    def description(self) -> str:
        """Description prefixed with the MCP server source."""
        source = f"[MCP: {self._info.server_name}] "
        return source + (
            self._info.description
            or f"Tool '{self._info.tool_name}' from MCP server '{self._info.server_name}'"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for the tool's input arguments."""
        return self._info.input_schema or {"type": "object", "properties": {}}

    @property
    def risk_level(self) -> RiskLevel:
        """Risk classification (inherited from server config)."""
        return self._risk_level

    def execute(self, args: dict[str, Any]) -> ToolResult:
        """Execute the MCP tool (sync wrapper around async call).

        ``AgentRuntime`` invokes tools via ``asyncio.to_thread``, so this
        method may be called from a worker thread while the event loop runs
        in the main thread.  We handle both cases:

        * No running loop -- use ``asyncio.run`` directly.
        * Running loop in another thread -- spin up a temporary thread pool.
        """
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # We are in a worker thread while the main loop runs elsewhere.
                # Create a fresh event loop in a throwaway thread.
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, self._async_execute(args))
                    result = future.result(timeout=60)
            else:
                result = asyncio.run(self._async_execute(args))

            if result.is_error:
                return ToolResult(output=result.content, error=result.content)
            return ToolResult(output=result.content)
        except Exception as exc:
            return ToolResult(output="", error=f"MCP tool execution failed: {exc}")

    async def _async_execute(self, args: dict[str, Any]) -> McpToolResult:
        """Async execution of the MCP tool call."""
        return await self._session.call_tool(self._info.tool_name, args)
