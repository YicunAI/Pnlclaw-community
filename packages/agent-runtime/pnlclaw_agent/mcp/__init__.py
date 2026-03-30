"""MCP (Model Context Protocol) client module for PnLClaw agent runtime.

PnLClaw acts as an MCP Client, connecting to user-configured external MCP
Servers.  Each server's tools are wrapped as ``BaseTool`` subclasses and
registered in the shared ``ToolCatalog``.

Public API:
    - ``McpConfig`` / ``McpServerConfig`` — configuration models
    - ``McpTransport`` — stdio / SSE transport enum
    - ``McpToolInfo`` — tool metadata discovered from a server
    - ``McpServerStatus`` — runtime status of a server connection
    - ``McpClientSession`` — manages a single MCP server connection
    - ``McpToolWrapper`` — adapts an MCP tool to ``BaseTool``
    - ``McpRegistry`` — manages all MCP connections and tool registrations
"""

from __future__ import annotations

from pnlclaw_agent.mcp.types import (
    McpConfig,
    McpServerConfig,
    McpServerStatus,
    McpToolInfo,
    McpToolResult,
    McpTransport,
)

# Lazy imports for classes that depend on the optional `mcp` SDK.
# We re-export them here so callers can do:
#     from pnlclaw_agent.mcp import McpClientSession, McpToolWrapper, McpRegistry

from pnlclaw_agent.mcp.client import McpClientSession
from pnlclaw_agent.mcp.tool_wrapper import McpToolWrapper
from pnlclaw_agent.mcp.registry import McpRegistry

__all__ = [
    "McpConfig",
    "McpClientSession",
    "McpRegistry",
    "McpServerConfig",
    "McpServerStatus",
    "McpToolInfo",
    "McpToolResult",
    "McpToolWrapper",
    "McpTransport",
]
