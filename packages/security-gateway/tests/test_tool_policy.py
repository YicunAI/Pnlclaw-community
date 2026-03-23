"""Tests for pnlclaw_security.tool_policy."""

from pnlclaw_security.tool_policy import (
    TOOL_GROUPS,
    ToolPolicy,
    ToolPolicyEngine,
    expand_tool_groups,
    normalize_tool_name,
)
from pnlclaw_types import RiskLevel

# ---------------------------------------------------------------------------
# normalize_tool_name
# ---------------------------------------------------------------------------


class TestNormalizeToolName:
    def test_lowercase(self) -> None:
        assert normalize_tool_name("Shell_Exec") == "shell_exec"

    def test_hyphen_to_underscore(self) -> None:
        assert normalize_tool_name("market-ticker") == "market_ticker"

    def test_strip_whitespace(self) -> None:
        assert normalize_tool_name("  market_ticker  ") == "market_ticker"

    def test_alias_bash(self) -> None:
        assert normalize_tool_name("bash") == "shell_exec"

    def test_alias_exec(self) -> None:
        assert normalize_tool_name("exec") == "shell_exec"

    def test_alias_apply_patch(self) -> None:
        assert normalize_tool_name("apply-patch") == "file_write"

    def test_mixed_case_hyphen_alias(self) -> None:
        assert normalize_tool_name("Apply-Patch") == "file_write"

    def test_unknown_tool_unchanged(self) -> None:
        assert normalize_tool_name("my_custom_tool") == "my_custom_tool"


# ---------------------------------------------------------------------------
# expand_tool_groups
# ---------------------------------------------------------------------------


class TestExpandToolGroups:
    def test_expand_market_read(self) -> None:
        result = expand_tool_groups(["group:market-read"])
        assert "market_ticker" in result
        assert "market_kline" in result
        assert "market_orderbook" in result

    def test_expand_mixed(self) -> None:
        result = expand_tool_groups(["group:market-read", "custom_tool"])
        assert "custom_tool" in result
        assert "market_ticker" in result

    def test_expand_unknown_group_dropped(self) -> None:
        result = expand_tool_groups(["group:nonexistent", "market_ticker"])
        assert result == ["market_ticker"]

    def test_deduplication(self) -> None:
        result = expand_tool_groups(["market_ticker", "market_ticker"])
        assert result.count("market_ticker") == 1

    def test_normalises_entries(self) -> None:
        result = expand_tool_groups(["Market-Ticker"])
        assert "market_ticker" in result

    def test_safe_group_contains_read_groups(self) -> None:
        safe = set(TOOL_GROUPS["group:safe"])
        for tool in TOOL_GROUPS["group:market-read"]:
            assert tool in safe
        for tool in TOOL_GROUPS["group:strategy-read"]:
            assert tool in safe


# ---------------------------------------------------------------------------
# ToolPolicyEngine — deny-first semantics
# ---------------------------------------------------------------------------


class TestToolPolicyEngineDenyFirst:
    def test_deny_overrides_allow(self) -> None:
        """If a tool is in both allow and deny, it must be blocked (deny-first)."""
        engine = ToolPolicyEngine([ToolPolicy(allow=["shell_exec"], deny=["shell_exec"])])
        assert engine.is_tool_allowed("shell_exec") is False

    def test_deny_group_overrides_allow(self) -> None:
        engine = ToolPolicyEngine([ToolPolicy(allow=["market_ticker"], deny=["group:market-read"])])
        assert engine.is_tool_allowed("market_ticker") is False

    def test_denied_via_alias(self) -> None:
        """Denying 'bash' must block 'shell_exec' (alias resolution)."""
        engine = ToolPolicyEngine([ToolPolicy(deny=["bash"])])
        assert engine.is_tool_allowed("shell_exec") is False
        assert engine.is_tool_allowed("bash") is False

    def test_denied_case_insensitive(self) -> None:
        engine = ToolPolicyEngine([ToolPolicy(deny=["Shell_Exec"])])
        assert engine.is_tool_allowed("shell_exec") is False
        assert engine.is_tool_allowed("SHELL_EXEC") is False


class TestToolPolicyEngineAllowList:
    def test_explicit_allow_blocks_unlisted(self) -> None:
        engine = ToolPolicyEngine([ToolPolicy(allow=["market_ticker"])])
        assert engine.is_tool_allowed("market_ticker") is True
        assert engine.is_tool_allowed("shell_exec") is False

    def test_no_allow_means_permit_all(self) -> None:
        """No allow list = all non-denied tools permitted."""
        engine = ToolPolicyEngine([ToolPolicy(deny=["shell_exec"])])
        assert engine.is_tool_allowed("market_ticker") is True
        assert engine.is_tool_allowed("shell_exec") is False

    def test_empty_policies_allow_everything(self) -> None:
        engine = ToolPolicyEngine([])
        assert engine.is_tool_allowed("shell_exec") is True
        assert engine.is_tool_allowed("market_ticker") is True

    def test_none_policies_allow_everything(self) -> None:
        engine = ToolPolicyEngine(None)
        assert engine.is_tool_allowed("anything") is True


class TestToolPolicyEngineMultiplePolicies:
    def test_deny_from_any_policy_blocks(self) -> None:
        engine = ToolPolicyEngine(
            [
                ToolPolicy(deny=["shell_exec"]),
                ToolPolicy(allow=["shell_exec", "market_ticker"]),
            ]
        )
        assert engine.is_tool_allowed("shell_exec") is False
        assert engine.is_tool_allowed("market_ticker") is True

    def test_allow_union_across_policies(self) -> None:
        engine = ToolPolicyEngine(
            [
                ToolPolicy(allow=["market_ticker"]),
                ToolPolicy(allow=["market_kline"]),
            ]
        )
        assert engine.is_tool_allowed("market_ticker") is True
        assert engine.is_tool_allowed("market_kline") is True
        assert engine.is_tool_allowed("shell_exec") is False


# ---------------------------------------------------------------------------
# classify_tool
# ---------------------------------------------------------------------------


class TestClassifyTool:
    def test_dangerous_tools(self) -> None:
        engine = ToolPolicyEngine([])
        assert engine.classify_tool("shell_exec") == RiskLevel.DANGEROUS
        assert engine.classify_tool("file_write") == RiskLevel.DANGEROUS
        assert engine.classify_tool("network_fetch") == RiskLevel.DANGEROUS

    def test_restricted_tools(self) -> None:
        engine = ToolPolicyEngine([])
        assert engine.classify_tool("backtest_run") == RiskLevel.RESTRICTED
        assert engine.classify_tool("paper_place_order") == RiskLevel.RESTRICTED

    def test_safe_tools(self) -> None:
        engine = ToolPolicyEngine([])
        assert engine.classify_tool("market_ticker") == RiskLevel.SAFE
        assert engine.classify_tool("explain_pnl") == RiskLevel.SAFE

    def test_unknown_tool_defaults_safe(self) -> None:
        engine = ToolPolicyEngine([])
        assert engine.classify_tool("some_custom_tool") == RiskLevel.SAFE

    def test_denied_tool_is_blocked(self) -> None:
        engine = ToolPolicyEngine([ToolPolicy(deny=["market_ticker"])])
        assert engine.classify_tool("market_ticker") == RiskLevel.BLOCKED

    def test_alias_classification(self) -> None:
        engine = ToolPolicyEngine([])
        assert engine.classify_tool("bash") == RiskLevel.DANGEROUS
