"""Tests for McpToolWrapper -- name formatting, description, parameters, and execution."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from pnlclaw_agent.mcp.tool_wrapper import McpToolWrapper, _sanitize_name
from pnlclaw_agent.mcp.types import McpToolInfo, McpToolResult
from pnlclaw_types.risk import RiskLevel


# ---------------------------------------------------------------------------
# _sanitize_name unit tests
# ---------------------------------------------------------------------------


class TestSanitizeName:
    def test_alphanumeric_unchanged(self) -> None:
        assert _sanitize_name("hello_world") == "hello_world"

    def test_uppercase_lowered(self) -> None:
        assert _sanitize_name("HelloWorld") == "helloworld"

    def test_special_chars_replaced(self) -> None:
        assert _sanitize_name("my-tool.v2") == "my_tool_v2"

    def test_leading_trailing_underscores_stripped(self) -> None:
        assert _sanitize_name("__test__") == "test"

    def test_multiple_special_chars(self) -> None:
        assert _sanitize_name("a@b#c$d") == "a_b_c_d"

    def test_empty_after_sanitize(self) -> None:
        # Edge case: all special chars
        result = _sanitize_name("---")
        assert result == ""

    def test_spaces_replaced(self) -> None:
        assert _sanitize_name("my tool") == "my_tool"

    def test_mixed_case_and_symbols(self) -> None:
        assert _sanitize_name("Server-Name.V2") == "server_name_v2"


# ---------------------------------------------------------------------------
# Mock MCP session
# ---------------------------------------------------------------------------


class _MockMcpSession:
    """Mock session that returns predetermined results for call_tool."""

    def __init__(
        self,
        result: McpToolResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self._result = result or McpToolResult(content="mock result")
        self._error = error

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> McpToolResult:
        if self._error:
            raise self._error
        return self._result


# ---------------------------------------------------------------------------
# McpToolWrapper -- name property
# ---------------------------------------------------------------------------


class TestMcpToolWrapperName:
    def _make_wrapper(
        self,
        server_name: str = "test-server",
        tool_name: str = "my_tool",
        **kwargs: Any,
    ) -> McpToolWrapper:
        info = McpToolInfo(
            server_name=server_name,
            tool_name=tool_name,
            description=kwargs.get("description", "Test tool"),
            input_schema=kwargs.get("input_schema", {}),
        )
        return McpToolWrapper(
            session=_MockMcpSession(),
            tool_info=info,
            risk_level=kwargs.get("risk_level", RiskLevel.RESTRICTED),
        )

    def test_basic_name_format(self) -> None:
        """Name should follow mcp_{server}_{tool} pattern."""
        wrapper = self._make_wrapper(server_name="filesystem", tool_name="read_file")
        assert wrapper.name == "mcp_filesystem_read_file"

    def test_name_sanitized(self) -> None:
        """Special chars in server/tool names should be replaced with underscores."""
        wrapper = self._make_wrapper(server_name="my-server.v2", tool_name="get-data")
        assert wrapper.name == "mcp_my_server_v2_get_data"

    def test_name_lowercased(self) -> None:
        wrapper = self._make_wrapper(server_name="MyServer", tool_name="ReadFile")
        assert wrapper.name == "mcp_myserver_readfile"

    def test_name_with_numbers(self) -> None:
        wrapper = self._make_wrapper(server_name="server1", tool_name="tool2")
        assert wrapper.name == "mcp_server1_tool2"

    def test_name_already_clean(self) -> None:
        wrapper = self._make_wrapper(server_name="clean", tool_name="tool")
        assert wrapper.name == "mcp_clean_tool"


# ---------------------------------------------------------------------------
# McpToolWrapper -- description property
# ---------------------------------------------------------------------------


class TestMcpToolWrapperDescription:
    def test_description_includes_server_name(self) -> None:
        info = McpToolInfo(
            server_name="filesystem",
            tool_name="read_file",
            description="Reads a file from disk",
        )
        wrapper = McpToolWrapper(session=_MockMcpSession(), tool_info=info)
        desc = wrapper.description

        assert "[MCP: filesystem]" in desc
        assert "Reads a file from disk" in desc

    def test_description_fallback_when_empty(self) -> None:
        """When tool has no description, a generic one is generated."""
        info = McpToolInfo(
            server_name="myserver",
            tool_name="mytool",
            description="",
        )
        wrapper = McpToolWrapper(session=_MockMcpSession(), tool_info=info)
        desc = wrapper.description

        assert "[MCP: myserver]" in desc
        assert "mytool" in desc
        assert "myserver" in desc


# ---------------------------------------------------------------------------
# McpToolWrapper -- parameters property
# ---------------------------------------------------------------------------


class TestMcpToolWrapperParameters:
    def test_passthrough_schema(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "encoding": {"type": "string", "default": "utf-8"},
            },
            "required": ["path"],
        }
        info = McpToolInfo(
            server_name="s", tool_name="t", input_schema=schema
        )
        wrapper = McpToolWrapper(session=_MockMcpSession(), tool_info=info)
        assert wrapper.parameters == schema

    def test_empty_schema_fallback(self) -> None:
        """When input_schema is empty, a default object schema is returned."""
        info = McpToolInfo(server_name="s", tool_name="t", input_schema={})
        wrapper = McpToolWrapper(session=_MockMcpSession(), tool_info=info)
        params = wrapper.parameters
        assert params == {"type": "object", "properties": {}}

    def test_none_schema_fallback(self) -> None:
        """When input_schema is falsy, a default object schema is returned."""
        info = McpToolInfo(server_name="s", tool_name="t")
        # input_schema defaults to {} via Field default_factory
        wrapper = McpToolWrapper(session=_MockMcpSession(), tool_info=info)
        params = wrapper.parameters
        assert "type" in params


# ---------------------------------------------------------------------------
# McpToolWrapper -- risk_level
# ---------------------------------------------------------------------------


class TestMcpToolWrapperRiskLevel:
    def test_default_risk_level(self) -> None:
        info = McpToolInfo(server_name="s", tool_name="t")
        wrapper = McpToolWrapper(session=_MockMcpSession(), tool_info=info)
        assert wrapper.risk_level == RiskLevel.RESTRICTED

    def test_custom_risk_level(self) -> None:
        info = McpToolInfo(server_name="s", tool_name="t")
        wrapper = McpToolWrapper(
            session=_MockMcpSession(), tool_info=info, risk_level=RiskLevel.DANGEROUS
        )
        assert wrapper.risk_level == RiskLevel.DANGEROUS

    def test_safe_risk_level(self) -> None:
        info = McpToolInfo(server_name="s", tool_name="t")
        wrapper = McpToolWrapper(
            session=_MockMcpSession(), tool_info=info, risk_level=RiskLevel.SAFE
        )
        assert wrapper.risk_level == RiskLevel.SAFE


# ---------------------------------------------------------------------------
# McpToolWrapper -- execute
# ---------------------------------------------------------------------------


class TestMcpToolWrapperExecute:
    def test_successful_execution(self) -> None:
        session = _MockMcpSession(result=McpToolResult(content="OK result"))
        info = McpToolInfo(server_name="s", tool_name="t")
        wrapper = McpToolWrapper(session=session, tool_info=info)

        result = wrapper.execute({"arg": "value"})
        assert result.output == "OK result"
        assert result.error is None

    def test_error_result_from_mcp(self) -> None:
        """MCP tool returning is_error=True should set ToolResult.error."""
        session = _MockMcpSession(
            result=McpToolResult(content="Tool failed", is_error=True)
        )
        info = McpToolInfo(server_name="s", tool_name="t")
        wrapper = McpToolWrapper(session=session, tool_info=info)

        result = wrapper.execute({})
        assert result.error == "Tool failed"
        assert result.output == "Tool failed"

    def test_exception_during_execution(self) -> None:
        """Exceptions during MCP call should be caught and returned as error."""
        session = _MockMcpSession(error=RuntimeError("Connection lost"))
        info = McpToolInfo(server_name="s", tool_name="t")
        wrapper = McpToolWrapper(session=session, tool_info=info)

        result = wrapper.execute({})
        assert result.error is not None
        assert "MCP tool execution failed" in result.error

    def test_execute_empty_args(self) -> None:
        session = _MockMcpSession(result=McpToolResult(content="no args"))
        info = McpToolInfo(server_name="s", tool_name="t")
        wrapper = McpToolWrapper(session=session, tool_info=info)

        result = wrapper.execute({})
        assert result.output == "no args"


# ---------------------------------------------------------------------------
# McpToolWrapper -- to_definition (inherited from BaseTool)
# ---------------------------------------------------------------------------


class TestMcpToolWrapperDefinition:
    def test_to_definition(self) -> None:
        info = McpToolInfo(
            server_name="filesystem",
            tool_name="read_file",
            description="Reads a file",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        )
        wrapper = McpToolWrapper(session=_MockMcpSession(), tool_info=info)
        defn = wrapper.to_definition()

        assert defn["name"] == "mcp_filesystem_read_file"
        assert "Reads a file" in defn["description"]
        assert "path" in defn["parameters"]["properties"]
