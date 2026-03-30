"""MCP type definitions for PnLClaw agent runtime."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from pnlclaw_types.risk import RiskLevel


class McpTransport(str, Enum):
    """MCP server transport type."""

    STDIO = "stdio"
    SSE = "sse"


class McpServerConfig(BaseModel):
    """Configuration for a single MCP server."""

    command: str | None = Field(None, description="Command to run (stdio transport)")
    args: list[str] = Field(default_factory=list, description="Command arguments (stdio)")
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables for the server process",
    )
    cwd: str | None = Field(None, description="Working directory for the server process")
    url: str | None = Field(None, description="Server URL (SSE transport)")
    transport: McpTransport = Field(McpTransport.STDIO, description="Transport type")
    enabled: bool = Field(True, description="Whether this server is active")
    risk_level: RiskLevel = Field(
        RiskLevel.RESTRICTED,
        description="Default risk level for tools from this server",
    )

    def validate_config(self) -> list[str]:
        """Validate that the config is complete for its transport type.

        Returns:
            List of error strings (empty means valid).
        """
        errors: list[str] = []
        if self.transport == McpTransport.STDIO and not self.command:
            errors.append("stdio transport requires 'command' field")
        if self.transport == McpTransport.SSE and not self.url:
            errors.append("SSE transport requires 'url' field")
        return errors


class McpConfig(BaseModel):
    """Top-level MCP configuration."""

    servers: dict[str, McpServerConfig] = Field(
        default_factory=dict, description="Named MCP server configs"
    )


class McpToolInfo(BaseModel):
    """Information about a tool discovered from an MCP server."""

    server_name: str = Field(..., description="Name of the MCP server providing this tool")
    tool_name: str = Field(..., description="Original tool name from the MCP server")
    description: str = Field("", description="Tool description")
    input_schema: dict[str, Any] = Field(
        default_factory=dict, description="JSON Schema for tool input"
    )


class McpToolResult(BaseModel):
    """Result from calling an MCP tool."""

    content: str = Field("", description="Text content of the result")
    is_error: bool = Field(False, description="Whether the result represents an error")


class McpServerStatus(BaseModel):
    """Runtime status of an MCP server connection."""

    name: str
    config: McpServerConfig
    connected: bool = False
    tool_count: int = 0
    error: str | None = None
    tools: list[McpToolInfo] = Field(default_factory=list)
