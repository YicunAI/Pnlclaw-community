"""Tool catalog — registry for agent tools with risk-level filtering.

The catalog integrates with ``ToolPolicyEngine`` from security-gateway
to enforce allow/deny policies before tools are exposed to the LLM.
"""

from __future__ import annotations

from typing import Any

from pnlclaw_agent.tools.base import BaseTool
from pnlclaw_types.risk import RiskLevel


class ToolCatalogError(Exception):
    """Raised when a tool catalog operation fails."""


class ToolCatalog:
    """Registry of agent tools with risk-level classification.

    Integrates with ``ToolPolicyEngine`` (from security-gateway) to filter
    tools by the current allow/deny policy.  If no policy engine is provided,
    all registered tools are considered allowed.
    """

    def __init__(self, policy_engine: Any | None = None) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._policy_engine = policy_engine

    # -- registration --------------------------------------------------------

    def register(self, tool: BaseTool) -> None:
        """Register a tool by its canonical name.

        Raises:
            ToolCatalogError: If a tool with the same name is already registered.
        """
        if tool.name in self._tools:
            raise ToolCatalogError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

    def register_many(self, tools: list[BaseTool]) -> None:
        """Register multiple tools at once."""
        for tool in tools:
            self.register(tool)

    # -- lookup --------------------------------------------------------------

    def get(self, name: str) -> BaseTool | None:
        """Look up a tool by canonical name."""
        return self._tools.get(name)

    def list_tools(self, risk_level: RiskLevel | None = None) -> list[BaseTool]:
        """List all registered tools, optionally filtered by risk level."""
        tools = list(self._tools.values())
        if risk_level is not None:
            tools = [t for t in tools if t.risk_level == risk_level]
        return sorted(tools, key=lambda t: t.name)

    def list_allowed_tools(self) -> list[BaseTool]:
        """List only tools that pass the current policy engine checks.

        If no policy engine is configured, all tools are returned.
        """
        if self._policy_engine is None:
            return self.list_tools()
        return sorted(
            [t for t in self._tools.values() if self._policy_engine.is_tool_allowed(t.name)],
            key=lambda t: t.name,
        )

    # -- LLM integration -----------------------------------------------------

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Return tool definitions for LLM function-calling prompt injection.

        Only includes tools that pass the policy engine check.
        Returns a list of ``{name, description, parameters}`` dicts.
        """
        return [t.to_definition() for t in self.list_allowed_tools()]

    # -- policy integration --------------------------------------------------

    def is_tool_allowed(self, name: str) -> bool:
        """Check if a tool is allowed by the current policy.

        Returns True if no policy engine is configured.
        """
        if self._policy_engine is None:
            return True
        return bool(self._policy_engine.is_tool_allowed(name))

    # -- info ----------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._tools)

    def tool_names(self) -> list[str]:
        """Return sorted list of all registered tool names."""
        return sorted(self._tools.keys())
