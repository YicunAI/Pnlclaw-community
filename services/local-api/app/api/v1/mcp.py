"""MCP server management endpoints.

Provides CRUD operations for MCP server configurations and status inspection.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.dependencies import AuthenticatedUser, get_mcp_registry, optional_user

router = APIRouter(prefix="/mcp", tags=["mcp"])


def _user_prefix(user: AuthenticatedUser, name: str) -> str:
    """Namespace MCP server names by user_id in Pro mode."""
    if user.id == "local":
        return name
    return f"{user.id}:{name}"


def _strip_prefix(user: AuthenticatedUser, prefixed: str) -> str | None:
    """Strip user prefix and return original name, or None if not owned."""
    if user.id == "local":
        return prefixed
    prefix = f"{user.id}:"
    if prefixed.startswith(prefix):
        return prefixed[len(prefix) :]
    return None


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class McpServerCreateRequest(BaseModel):
    """Request body for adding a new MCP server."""

    command: str | None = Field(None, description="Command to run (stdio)")
    args: list[str] = Field(default_factory=list, description="Command arguments")
    env: dict[str, str] = Field(default_factory=dict, description="Environment variables")
    cwd: str | None = Field(None, description="Working directory")
    url: str | None = Field(None, description="Server URL (SSE)")
    transport: str = Field("stdio", description="Transport type: stdio or sse")
    enabled: bool = Field(True, description="Whether the server is active")
    risk_level: str = Field("restricted", description="Default risk level for tools")


class McpServerResponse(BaseModel):
    """Response model for an MCP server status."""

    name: str
    connected: bool = False
    tool_count: int = 0
    error: str | None = None
    transport: str = "stdio"
    tools: list[dict[str, Any]] = Field(default_factory=list)


class McpToolResponse(BaseModel):
    """Response model for an MCP tool."""

    server_name: str
    tool_name: str
    registered_name: str
    description: str = ""


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/servers")
async def list_mcp_servers(
    registry: Any = Depends(get_mcp_registry),
    user: AuthenticatedUser = Depends(optional_user),
) -> dict[str, Any]:
    """List MCP servers owned by the current user."""
    if registry is None:
        return {"servers": [], "message": "MCP registry not initialized"}

    servers = registry.list_servers()
    result = []
    for s in servers:
        display_name = _strip_prefix(user, s.name)
        if display_name is None:
            continue
        result.append(
            {
                "name": display_name,
                "connected": s.connected,
                "tool_count": s.tool_count,
                "error": s.error,
                "transport": s.config.transport.value if hasattr(s.config, "transport") else "stdio",
                "tools": [
                    {"server_name": display_name, "tool_name": t.tool_name, "description": t.description}
                    for t in s.tools
                ],
            }
        )
    return {"servers": result}


@router.post("/servers/{name}")
async def add_mcp_server(
    name: str,
    body: McpServerCreateRequest,
    registry: Any = Depends(get_mcp_registry),
    user: AuthenticatedUser = Depends(optional_user),
) -> dict[str, Any]:
    """Add and connect a new MCP server (scoped to current user)."""
    if registry is None:
        raise HTTPException(503, "MCP registry not initialized")

    from pnlclaw_agent.mcp.types import McpServerConfig, McpTransport
    from pnlclaw_types.risk import RiskLevel

    transport = McpTransport(body.transport) if body.transport in ("stdio", "sse") else McpTransport.STDIO
    risk_map = {"safe": RiskLevel.SAFE, "restricted": RiskLevel.RESTRICTED, "dangerous": RiskLevel.DANGEROUS}
    risk_level = risk_map.get(body.risk_level, RiskLevel.RESTRICTED)

    config = McpServerConfig(
        command=body.command,
        args=body.args,
        env=body.env,
        cwd=body.cwd,
        url=body.url,
        transport=transport,
        enabled=body.enabled,
        risk_level=risk_level,
    )

    internal_name = _user_prefix(user, name)
    status = await registry.add_server(internal_name, config)
    return {
        "name": name,
        "connected": status.connected,
        "tool_count": status.tool_count,
        "error": status.error,
    }


@router.delete("/servers/{name}")
async def remove_mcp_server(
    name: str,
    registry: Any = Depends(get_mcp_registry),
    user: AuthenticatedUser = Depends(optional_user),
) -> dict[str, str]:
    """Remove an MCP server (must be owned by current user)."""
    if registry is None:
        raise HTTPException(503, "MCP registry not initialized")

    internal_name = _user_prefix(user, name)
    await registry.remove_server(internal_name)
    return {"status": "removed", "name": name}


@router.post("/servers/{name}/refresh")
async def refresh_mcp_server(
    name: str,
    registry: Any = Depends(get_mcp_registry),
    user: AuthenticatedUser = Depends(optional_user),
) -> dict[str, Any]:
    """Reconnect to an MCP server (must be owned by current user)."""
    if registry is None:
        raise HTTPException(503, "MCP registry not initialized")

    internal_name = _user_prefix(user, name)
    status = await registry.refresh_server(internal_name)
    return {
        "name": name,
        "connected": status.connected,
        "tool_count": status.tool_count,
        "error": status.error,
    }


@router.get("/tools")
async def list_mcp_tools(
    registry: Any = Depends(get_mcp_registry),
    user: AuthenticatedUser = Depends(optional_user),
) -> dict[str, Any]:
    """List tools from MCP servers owned by the current user."""
    if registry is None:
        return {"tools": []}

    tools = registry.list_mcp_tools()
    result = []
    for t in tools:
        display_name = _strip_prefix(user, t.server_name)
        if display_name is None:
            continue
        result.append(
            {
                "server_name": display_name,
                "tool_name": t.tool_name,
                "registered_name": f"mcp_{display_name}_{t.tool_name}",
                "description": t.description,
            }
        )
    return {"tools": result}
