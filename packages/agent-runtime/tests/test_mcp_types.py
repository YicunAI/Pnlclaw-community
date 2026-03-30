"""Tests for MCP type models: McpServerConfig, McpConfig, McpToolInfo, McpToolResult, McpServerStatus."""

from __future__ import annotations

import pytest

from pnlclaw_agent.mcp.types import (
    McpConfig,
    McpServerConfig,
    McpServerStatus,
    McpToolInfo,
    McpToolResult,
    McpTransport,
)
from pnlclaw_types.risk import RiskLevel


# ---------------------------------------------------------------------------
# McpTransport enum
# ---------------------------------------------------------------------------


class TestMcpTransport:
    def test_values(self) -> None:
        assert McpTransport.STDIO.value == "stdio"
        assert McpTransport.SSE.value == "sse"

    def test_all_members(self) -> None:
        assert len(list(McpTransport)) == 2

    def test_string_comparison(self) -> None:
        assert McpTransport.STDIO == "stdio"
        assert McpTransport.SSE == "sse"


# ---------------------------------------------------------------------------
# McpServerConfig
# ---------------------------------------------------------------------------


class TestMcpServerConfig:
    def test_defaults(self) -> None:
        config = McpServerConfig()
        assert config.command is None
        assert config.args == []
        assert config.env == {}
        assert config.cwd is None
        assert config.url is None
        assert config.transport == McpTransport.STDIO
        assert config.enabled is True
        assert config.risk_level == RiskLevel.RESTRICTED

    def test_stdio_config(self) -> None:
        config = McpServerConfig(
            command="npx",
            args=["-y", "@anthropic/mcp-server-filesystem"],
            transport=McpTransport.STDIO,
        )
        assert config.command == "npx"
        assert config.args == ["-y", "@anthropic/mcp-server-filesystem"]
        assert config.transport == McpTransport.STDIO

    def test_sse_config(self) -> None:
        config = McpServerConfig(
            url="https://mcp.example.com/sse",
            transport=McpTransport.SSE,
        )
        assert config.url == "https://mcp.example.com/sse"
        assert config.transport == McpTransport.SSE

    def test_custom_env_and_cwd(self) -> None:
        config = McpServerConfig(
            command="python",
            args=["server.py"],
            env={"API_KEY": "secret"},
            cwd="/opt/mcp",
        )
        assert config.env == {"API_KEY": "secret"}
        assert config.cwd == "/opt/mcp"

    def test_disabled(self) -> None:
        config = McpServerConfig(enabled=False)
        assert config.enabled is False

    def test_custom_risk_level(self) -> None:
        config = McpServerConfig(risk_level=RiskLevel.DANGEROUS)
        assert config.risk_level == RiskLevel.DANGEROUS

    # -- validate_config -------------------------------------------------------

    def test_validate_stdio_requires_command(self) -> None:
        """stdio transport without command should report an error."""
        config = McpServerConfig(transport=McpTransport.STDIO, command=None)
        errors = config.validate_config()
        assert len(errors) == 1
        assert "command" in errors[0].lower()

    def test_validate_stdio_with_command_ok(self) -> None:
        config = McpServerConfig(transport=McpTransport.STDIO, command="npx")
        errors = config.validate_config()
        assert errors == []

    def test_validate_sse_requires_url(self) -> None:
        """SSE transport without url should report an error."""
        config = McpServerConfig(transport=McpTransport.SSE, url=None)
        errors = config.validate_config()
        assert len(errors) == 1
        assert "url" in errors[0].lower()

    def test_validate_sse_with_url_ok(self) -> None:
        config = McpServerConfig(
            transport=McpTransport.SSE, url="https://example.com/sse"
        )
        errors = config.validate_config()
        assert errors == []

    def test_serialization_roundtrip(self) -> None:
        config = McpServerConfig(
            command="node",
            args=["server.js"],
            env={"PORT": "3000"},
            transport=McpTransport.STDIO,
            risk_level=RiskLevel.SAFE,
        )
        data = config.model_dump()
        restored = McpServerConfig.model_validate(data)
        assert restored.command == "node"
        assert restored.risk_level == RiskLevel.SAFE


# ---------------------------------------------------------------------------
# McpConfig
# ---------------------------------------------------------------------------


class TestMcpConfig:
    def test_empty_config(self) -> None:
        config = McpConfig()
        assert config.servers == {}

    def test_multiple_servers(self) -> None:
        config = McpConfig(
            servers={
                "filesystem": McpServerConfig(
                    command="npx", transport=McpTransport.STDIO
                ),
                "remote": McpServerConfig(
                    url="https://mcp.example.com/sse",
                    transport=McpTransport.SSE,
                    enabled=False,
                ),
            }
        )
        assert len(config.servers) == 2
        assert "filesystem" in config.servers
        assert "remote" in config.servers
        assert config.servers["remote"].enabled is False

    def test_serialization(self) -> None:
        config = McpConfig(
            servers={"test": McpServerConfig(command="echo")}
        )
        data = config.model_dump()
        assert "test" in data["servers"]

        restored = McpConfig.model_validate(data)
        assert restored.servers["test"].command == "echo"


# ---------------------------------------------------------------------------
# McpToolInfo
# ---------------------------------------------------------------------------


class TestMcpToolInfo:
    def test_basic(self) -> None:
        info = McpToolInfo(
            server_name="filesystem",
            tool_name="read_file",
            description="Reads a file from disk",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        )
        assert info.server_name == "filesystem"
        assert info.tool_name == "read_file"
        assert info.description == "Reads a file from disk"
        assert "path" in info.input_schema["properties"]

    def test_defaults(self) -> None:
        info = McpToolInfo(server_name="s", tool_name="t")
        assert info.description == ""
        assert info.input_schema == {}

    def test_serialization(self) -> None:
        info = McpToolInfo(
            server_name="s", tool_name="t", description="d"
        )
        data = info.model_dump()
        restored = McpToolInfo.model_validate(data)
        assert restored.server_name == "s"
        assert restored.tool_name == "t"


# ---------------------------------------------------------------------------
# McpToolResult
# ---------------------------------------------------------------------------


class TestMcpToolResult:
    def test_success_result(self) -> None:
        result = McpToolResult(content="File contents here")
        assert result.content == "File contents here"
        assert result.is_error is False

    def test_error_result(self) -> None:
        result = McpToolResult(content="File not found", is_error=True)
        assert result.content == "File not found"
        assert result.is_error is True

    def test_defaults(self) -> None:
        result = McpToolResult()
        assert result.content == ""
        assert result.is_error is False

    def test_serialization(self) -> None:
        result = McpToolResult(content="data", is_error=False)
        data = result.model_dump()
        assert data["content"] == "data"
        assert data["is_error"] is False

        restored = McpToolResult.model_validate(data)
        assert restored.content == "data"


# ---------------------------------------------------------------------------
# McpServerStatus
# ---------------------------------------------------------------------------


class TestMcpServerStatus:
    def test_defaults(self) -> None:
        status = McpServerStatus(name="test", config=McpServerConfig())
        assert status.name == "test"
        assert status.connected is False
        assert status.tool_count == 0
        assert status.error is None
        assert status.tools == []

    def test_connected_with_tools(self) -> None:
        tools = [
            McpToolInfo(server_name="s", tool_name="t1", description="Tool 1"),
            McpToolInfo(server_name="s", tool_name="t2", description="Tool 2"),
        ]
        status = McpServerStatus(
            name="s",
            config=McpServerConfig(command="node"),
            connected=True,
            tool_count=2,
            tools=tools,
        )
        assert status.connected is True
        assert status.tool_count == 2
        assert len(status.tools) == 2

    def test_error_status(self) -> None:
        status = McpServerStatus(
            name="failed",
            config=McpServerConfig(),
            connected=False,
            error="Connection refused",
        )
        assert status.error == "Connection refused"
        assert status.connected is False

    def test_serialization(self) -> None:
        status = McpServerStatus(
            name="test",
            config=McpServerConfig(command="echo"),
            connected=True,
            tool_count=1,
        )
        data = status.model_dump()
        restored = McpServerStatus.model_validate(data)
        assert restored.name == "test"
        assert restored.connected is True
