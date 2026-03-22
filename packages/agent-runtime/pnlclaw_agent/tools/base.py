"""BaseTool ABC and ToolResult — foundation for all agent tools.

Every tool in PnLClaw implements BaseTool.  Tools are sync (all Sprint 2
engines are sync); the async boundary lives in AgentRuntime which wraps
calls via ``asyncio.to_thread``.
"""

from __future__ import annotations

import abc
from typing import Any

from pydantic import BaseModel, Field

from pnlclaw_types.risk import RiskLevel


# ---------------------------------------------------------------------------
# ToolResult
# ---------------------------------------------------------------------------


class ToolResult(BaseModel):
    """Universal return type for tool execution.

    ``output`` always contains LLM-readable text.
    ``error`` is set only on failure.
    """

    output: str = Field(..., description="Human/LLM-readable result text")
    error: str | None = Field(None, description="Error message if execution failed")


# ---------------------------------------------------------------------------
# BaseTool ABC
# ---------------------------------------------------------------------------


class BaseTool(abc.ABC):
    """Abstract base class for all agent tools.

    Subclasses must define four properties and one method:

    * ``name``        – canonical tool name (must match security-gateway names).
    * ``description`` – 1-3 sentence description used in the LLM system prompt.
    * ``parameters``  – JSON Schema dict describing expected ``execute`` args.
    * ``risk_level``  – self-declared risk classification.
    * ``execute``     – sync execution returning a :class:`ToolResult`.
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Canonical tool name (e.g. ``'market_ticker'``)."""

    @property
    @abc.abstractmethod
    def description(self) -> str:
        """Short description for the LLM system prompt."""

    @property
    @abc.abstractmethod
    def parameters(self) -> dict[str, Any]:
        """JSON Schema describing the ``args`` dict for :meth:`execute`."""

    @property
    @abc.abstractmethod
    def risk_level(self) -> RiskLevel:
        """Risk classification: SAFE, RESTRICTED, DANGEROUS, or BLOCKED."""

    @abc.abstractmethod
    def execute(self, args: dict[str, Any]) -> ToolResult:
        """Execute the tool with the given arguments.

        Args:
            args: Dictionary of arguments matching :attr:`parameters`.

        Returns:
            A :class:`ToolResult` with formatted text output.
        """

    # -- convenience ---------------------------------------------------------

    def validate_args(self, args: dict[str, Any]) -> list[str]:
        """Basic validation of *args* against :attr:`parameters`.

        Checks ``required`` keys and top-level ``type`` constraints from the
        JSON Schema.  Returns a list of error strings (empty == valid).
        """
        schema = self.parameters
        errors: list[str] = []

        # Check required keys
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        for key in required:
            if key not in args:
                errors.append(f"Missing required parameter: {key}")

        # Check basic types for provided args
        _JSON_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }

        for key, value in args.items():
            if key in properties:
                expected_type = properties[key].get("type")
                if expected_type and expected_type in _JSON_TYPE_MAP:
                    py_type = _JSON_TYPE_MAP[expected_type]
                    if not isinstance(value, py_type):
                        errors.append(
                            f"Parameter '{key}' expected type '{expected_type}', "
                            f"got {type(value).__name__}"
                        )

        return errors

    def to_definition(self) -> dict[str, Any]:
        """Return a dict suitable for LLM tool/function definitions."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
