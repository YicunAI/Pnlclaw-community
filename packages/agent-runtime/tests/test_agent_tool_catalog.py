"""Tests for ToolCatalog — registration, filtering, and policy integration."""

from __future__ import annotations

from typing import Any

import pytest

from pnlclaw_agent.tool_catalog import ToolCatalog, ToolCatalogError
from pnlclaw_agent.tools.base import BaseTool, ToolResult
from pnlclaw_types.risk import RiskLevel
from pnlclaw_security.tool_policy import ToolPolicy, ToolPolicyEngine


# ---------------------------------------------------------------------------
# Helpers — concrete test tools
# ---------------------------------------------------------------------------


def _make_tool(name: str, risk: RiskLevel = RiskLevel.SAFE) -> BaseTool:
    """Create a minimal concrete tool for testing."""

    class _Tool(BaseTool):
        @property
        def name(self) -> str:
            return name

        @property
        def description(self) -> str:
            return f"Test tool: {name}"

        @property
        def parameters(self) -> dict[str, Any]:
            return {"type": "object", "properties": {}, "required": []}

        @property
        def risk_level(self) -> RiskLevel:
            return risk

        def execute(self, args: dict[str, Any]) -> ToolResult:
            return ToolResult(output=f"Executed {name}")

    return _Tool()


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_and_get(self) -> None:
        catalog = ToolCatalog()
        tool = _make_tool("market_ticker")
        catalog.register(tool)
        assert catalog.get("market_ticker") is tool

    def test_register_duplicate(self) -> None:
        catalog = ToolCatalog()
        catalog.register(_make_tool("market_ticker"))
        with pytest.raises(ToolCatalogError, match="already registered"):
            catalog.register(_make_tool("market_ticker"))

    def test_register_many(self) -> None:
        catalog = ToolCatalog()
        catalog.register_many([_make_tool("a"), _make_tool("b"), _make_tool("c")])
        assert len(catalog) == 3

    def test_get_unknown(self) -> None:
        catalog = ToolCatalog()
        assert catalog.get("nonexistent") is None

    def test_tool_names(self) -> None:
        catalog = ToolCatalog()
        catalog.register_many([_make_tool("c"), _make_tool("a"), _make_tool("b")])
        assert catalog.tool_names() == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# Filtering tests
# ---------------------------------------------------------------------------


class TestFiltering:
    def test_list_all(self) -> None:
        catalog = ToolCatalog()
        catalog.register_many([_make_tool("x"), _make_tool("y")])
        assert len(catalog.list_tools()) == 2

    def test_list_by_risk_level(self) -> None:
        catalog = ToolCatalog()
        catalog.register(_make_tool("safe_1", RiskLevel.SAFE))
        catalog.register(_make_tool("safe_2", RiskLevel.SAFE))
        catalog.register(_make_tool("restricted_1", RiskLevel.RESTRICTED))

        safe_tools = catalog.list_tools(risk_level=RiskLevel.SAFE)
        assert len(safe_tools) == 2

        restricted_tools = catalog.list_tools(risk_level=RiskLevel.RESTRICTED)
        assert len(restricted_tools) == 1
        assert restricted_tools[0].name == "restricted_1"


# ---------------------------------------------------------------------------
# Policy integration tests
# ---------------------------------------------------------------------------


class TestPolicyIntegration:
    def test_no_policy_all_allowed(self) -> None:
        catalog = ToolCatalog()
        catalog.register(_make_tool("anything"))
        assert catalog.is_tool_allowed("anything") is True
        assert len(catalog.list_allowed_tools()) == 1

    def test_policy_denies_tool(self) -> None:
        policy = ToolPolicyEngine([ToolPolicy(deny=["backtest_run"])])
        catalog = ToolCatalog(policy_engine=policy)
        catalog.register(_make_tool("market_ticker"))
        catalog.register(_make_tool("backtest_run", RiskLevel.RESTRICTED))

        assert catalog.is_tool_allowed("market_ticker") is True
        assert catalog.is_tool_allowed("backtest_run") is False

        allowed = catalog.list_allowed_tools()
        assert len(allowed) == 1
        assert allowed[0].name == "market_ticker"

    def test_policy_allow_list(self) -> None:
        policy = ToolPolicyEngine([
            ToolPolicy(allow=["group:market-read"]),
        ])
        catalog = ToolCatalog(policy_engine=policy)
        catalog.register(_make_tool("market_ticker"))
        catalog.register(_make_tool("backtest_run", RiskLevel.RESTRICTED))

        # Only market_ticker is in group:market-read
        allowed = catalog.list_allowed_tools()
        names = [t.name for t in allowed]
        assert "market_ticker" in names
        assert "backtest_run" not in names

    def test_get_tool_definitions(self) -> None:
        catalog = ToolCatalog()
        catalog.register(_make_tool("market_ticker"))
        catalog.register(_make_tool("risk_check"))

        defs = catalog.get_tool_definitions()
        assert len(defs) == 2
        assert all("name" in d and "description" in d and "parameters" in d for d in defs)

    def test_tool_definitions_respect_policy(self) -> None:
        policy = ToolPolicyEngine([ToolPolicy(deny=["risk_check"])])
        catalog = ToolCatalog(policy_engine=policy)
        catalog.register(_make_tool("market_ticker"))
        catalog.register(_make_tool("risk_check"))

        defs = catalog.get_tool_definitions()
        assert len(defs) == 1
        assert defs[0]["name"] == "market_ticker"
