"""Tests for BaseTool ABC and ToolResult."""

from __future__ import annotations

from typing import Any

import pytest

from pnlclaw_agent.tools.base import BaseTool, ToolResult
from pnlclaw_types.risk import RiskLevel


# ---------------------------------------------------------------------------
# Concrete test tool
# ---------------------------------------------------------------------------


class _EchoTool(BaseTool):
    """Minimal concrete tool for testing."""

    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "Echoes the input text."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to echo"},
            },
            "required": ["text"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.SAFE

    def execute(self, args: dict[str, Any]) -> ToolResult:
        text = args.get("text", "")
        return ToolResult(output=f"Echo: {text}")


# ---------------------------------------------------------------------------
# ToolResult tests
# ---------------------------------------------------------------------------


class TestToolResult:
    def test_success(self) -> None:
        result = ToolResult(output="OK")
        assert result.output == "OK"
        assert result.error is None

    def test_error(self) -> None:
        result = ToolResult(output="", error="Something went wrong")
        assert result.error == "Something went wrong"

    def test_serialization(self) -> None:
        result = ToolResult(output="data", error=None)
        data = result.model_dump()
        assert data == {"output": "data", "error": None}
        roundtrip = ToolResult.model_validate(data)
        assert roundtrip.output == "data"


# ---------------------------------------------------------------------------
# BaseTool tests
# ---------------------------------------------------------------------------


class TestBaseTool:
    def test_concrete_subclass(self) -> None:
        tool = _EchoTool()
        assert tool.name == "echo"
        assert tool.description == "Echoes the input text."
        assert tool.risk_level == RiskLevel.SAFE

    def test_execute(self) -> None:
        tool = _EchoTool()
        result = tool.execute({"text": "hello"})
        assert result.output == "Echo: hello"
        assert result.error is None

    def test_to_definition(self) -> None:
        tool = _EchoTool()
        defn = tool.to_definition()
        assert defn["name"] == "echo"
        assert defn["description"] == "Echoes the input text."
        assert "properties" in defn["parameters"]

    def test_validate_args_valid(self) -> None:
        tool = _EchoTool()
        errors = tool.validate_args({"text": "hello"})
        assert errors == []

    def test_validate_args_missing_required(self) -> None:
        tool = _EchoTool()
        errors = tool.validate_args({})
        assert len(errors) == 1
        assert "Missing required parameter: text" in errors[0]

    def test_validate_args_wrong_type(self) -> None:
        tool = _EchoTool()
        errors = tool.validate_args({"text": 123})
        assert len(errors) == 1
        assert "expected type 'string'" in errors[0]

    def test_validate_args_extra_keys_allowed(self) -> None:
        tool = _EchoTool()
        errors = tool.validate_args({"text": "hi", "extra": True})
        assert errors == []

    def test_abstract_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError):
            BaseTool()  # type: ignore[abstract]
