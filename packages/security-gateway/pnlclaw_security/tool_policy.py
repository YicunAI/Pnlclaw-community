"""Tool policy engine with deny-first semantics and group expansion.

Distilled from OpenClaw src/agents/tool-policy.ts.
Implements SE-01: All tool calls go through security-gateway allow/deny policy.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from pnlclaw_types import RiskLevel

# ---------------------------------------------------------------------------
# Tool name aliases — normalise common synonyms to canonical names
# ---------------------------------------------------------------------------
_TOOL_ALIASES: dict[str, str] = {
    "bash": "shell_exec",
    "exec": "shell_exec",
    "sh": "shell_exec",
    "apply_patch": "file_write",
    "apply-patch": "file_write",
}

# ---------------------------------------------------------------------------
# Pre-defined tool groups
# ---------------------------------------------------------------------------
TOOL_GROUPS: dict[str, list[str]] = {
    "group:market-read": [
        "market_ticker",
        "market_kline",
        "market_orderbook",
    ],
    "group:strategy-read": [
        "list_strategies",
        "get_strategy",
        "backtest_result",
    ],
    "group:info": [
        "explain_pnl",
        "explain_market",
        "risk_check",
        "risk_report",
        "paper_positions",
        "paper_pnl",
    ],
    "group:safe": [
        # Expanded at init from market-read + strategy-read + info
    ],
    "group:restricted": [
        "backtest_run",
        "paper_create_account",
        "paper_place_order",
        "paper_stop",
    ],
    "group:dangerous": [
        "shell_exec",
        "file_write",
        "file_read",
        "network_fetch",
        "config_modify",
    ],
}

# Build group:safe as union of read/info groups
TOOL_GROUPS["group:safe"] = sorted(
    set(TOOL_GROUPS["group:market-read"] + TOOL_GROUPS["group:strategy-read"] + TOOL_GROUPS["group:info"])
)

# Reverse lookup: tool_name → group label (for classification)
_TOOL_TO_RISK: dict[str, RiskLevel] = {}
for _name in TOOL_GROUPS["group:dangerous"]:
    _TOOL_TO_RISK[_name] = RiskLevel.DANGEROUS
for _name in TOOL_GROUPS["group:restricted"]:
    _TOOL_TO_RISK[_name] = RiskLevel.RESTRICTED
for _name in TOOL_GROUPS["group:safe"]:
    _TOOL_TO_RISK[_name] = RiskLevel.SAFE


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------


def normalize_tool_name(name: str) -> str:
    """Normalise a tool name: strip, lowercase, hyphen→underscore, resolve aliases.

    This prevents bypass via casing or punctuation variants such as
    ``Shell-Exec`` vs ``shell_exec``.
    """
    canonical = name.strip().lower().replace("-", "_")
    return _TOOL_ALIASES.get(canonical, canonical)


def expand_tool_groups(names: list[str]) -> list[str]:
    """Expand any ``group:*`` references in *names* to their member tools.

    Unknown group references are silently dropped (defensive).
    Returns a deduplicated, sorted list.
    """
    expanded: set[str] = set()
    for entry in names:
        stripped = entry.strip().lower()
        if stripped.startswith("group:"):
            # Try both hyphen and underscore variants for group lookup
            suffix = stripped[6:]
            hyphen_key = f"group:{suffix.replace('_', '-')}"
            underscore_key = f"group:{suffix.replace('-', '_')}"
            if hyphen_key in TOOL_GROUPS:
                expanded.update(TOOL_GROUPS[hyphen_key])
            elif underscore_key in TOOL_GROUPS:
                expanded.update(TOOL_GROUPS[underscore_key])
            # else: unknown group, silently ignore (deny-first: safer to drop)
        else:
            expanded.add(normalize_tool_name(entry))
    return sorted(expanded)


# ---------------------------------------------------------------------------
# Policy model
# ---------------------------------------------------------------------------


class ToolPolicy(BaseModel):
    """A single allow/deny policy layer.

    Multiple policies can be stacked in :class:`ToolPolicyEngine`.
    Deny entries always take precedence over allow entries.
    """

    allow: list[str] = Field(default_factory=list, description="Allowed tool names or group refs")
    deny: list[str] = Field(default_factory=list, description="Denied tool names or group refs")


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ToolPolicyEngine:
    """Deny-first tool policy engine.

    Evaluation rules (in order):
    1. If the normalised tool name is in *any* deny set → **blocked**.
    2. If *any* policy defines an allow set and the tool is not in
       the union of all allow sets → **blocked**.
    3. Otherwise → **allowed**.

    This ensures deny always wins, and an explicit allow-list acts as
    a whitelist (anything not listed is implicitly denied).
    """

    def __init__(self, policies: list[ToolPolicy] | None = None) -> None:
        policies = policies or []
        self._denied: frozenset[str] = frozenset()
        self._allowed: frozenset[str] | None = None  # None = no explicit allow → permit all
        self._rebuild(policies)

    # -- public API ----------------------------------------------------------

    def is_tool_allowed(self, tool_name: str) -> bool:
        """Return ``True`` if *tool_name* passes all policy layers."""
        normalised = normalize_tool_name(tool_name)

        # Rule 1: deny always wins
        if normalised in self._denied:
            return False

        # Rule 2: if there is an explicit allow-list, tool must be in it
        if self._allowed is not None and normalised not in self._allowed:
            return False

        return True

    def classify_tool(self, tool_name: str) -> RiskLevel:
        """Return the risk classification for *tool_name*.

        If the tool is explicitly denied by policy it is ``BLOCKED``.
        Otherwise the classification comes from the built-in group mapping,
        defaulting to ``SAFE`` for unknown tools.
        """
        normalised = normalize_tool_name(tool_name)

        if normalised in self._denied:
            return RiskLevel.BLOCKED

        return _TOOL_TO_RISK.get(normalised, RiskLevel.SAFE)

    # -- internal ------------------------------------------------------------

    def _rebuild(self, policies: list[ToolPolicy]) -> None:
        deny_set: set[str] = set()
        allow_set: set[str] = set()
        has_allow = False

        for policy in policies:
            if policy.deny:
                deny_set.update(expand_tool_groups(policy.deny))
            if policy.allow:
                has_allow = True
                allow_set.update(expand_tool_groups(policy.allow))

        self._denied = frozenset(deny_set)
        self._allowed = frozenset(allow_set) if has_allow else None
