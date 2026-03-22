"""System prompt builder — assembles the LLM system prompt from context.

Combines role instructions, tool descriptions, market context,
user preferences, and safety constraints into a single system prompt.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from typing import Any

from pnlclaw_types.agent import AgentRole, MarketState


# ---------------------------------------------------------------------------
# AgentContext
# ---------------------------------------------------------------------------


@dataclass
class AgentContext:
    """Context used to build the LLM system prompt.

    Attributes:
        role: Optional agent role for role-specific prompt.
        available_tools: Tool definitions from ToolCatalog.get_tool_definitions().
        market_state: Current market state if available.
        user_preferences: User preference dict (risk_appetite, etc.).
        active_symbols: Currently tracked trading pairs.
        memory_context: Recalled memory text for prompt injection.
    """

    role: AgentRole | None = None
    available_tools: list[dict[str, Any]] = field(default_factory=list)
    market_state: MarketState | None = None
    user_preferences: dict[str, Any] | None = None
    active_symbols: list[str] = field(default_factory=list)
    memory_context: str = ""


# ---------------------------------------------------------------------------
# Base prompt
# ---------------------------------------------------------------------------

_BASE_PROMPT = textwrap.dedent("""\
    You are PnLClaw, an AI quantitative trading assistant for crypto markets.
    You help users analyze markets, draft and validate trading strategies,
    run backtests, manage paper trading, and explain results.

    You operate within a security-gated environment. All trading operations
    are paper trading only — no real money is at risk.

    Always use the available tools to fetch data before making claims.
    Never fabricate prices, indicator values, or backtest results.
""")

_SAFETY_PROMPT = textwrap.dedent("""\

    ## Safety Constraints
    - Never expose API keys, secrets, or credentials in responses.
    - Tools marked as "restricted" require user confirmation before execution.
    - Tools marked as "dangerous" are blocked by default.
    - All trade intents must pass risk checks before execution.
    - You cannot access the filesystem, run shell commands, or make network requests directly.
""")


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_system_prompt(context: AgentContext) -> str:
    """Assemble the system prompt from the given context.

    Sections:
    1. Base role instruction (or role-specific from team/roles)
    2. Available tool descriptions
    3. Market context (if present)
    4. User preferences (if present)
    5. Memory context (if present)
    6. Safety constraints

    Args:
        context: The agent context containing role, tools, market state, etc.

    Returns:
        The complete system prompt string.
    """
    sections: list[str] = []

    # 1. Role instruction
    if context.role is not None:
        from pnlclaw_agent.team.roles import get_role
        role_def = get_role(context.role)
        sections.append(role_def.system_prompt)
    else:
        sections.append(_BASE_PROMPT)

    # 2. Available tools
    if context.available_tools:
        tool_lines = ["## Available Tools", ""]
        for tool_def in context.available_tools:
            name = tool_def.get("name", "unknown")
            desc = tool_def.get("description", "")
            params = tool_def.get("parameters", {})
            props = params.get("properties", {})
            required = params.get("required", [])

            param_parts = []
            for pname, pinfo in props.items():
                ptype = pinfo.get("type", "any")
                pdesc = pinfo.get("description", "")
                req_mark = " (required)" if pname in required else ""
                param_parts.append(f"    - {pname}: {ptype}{req_mark} — {pdesc}")

            tool_lines.append(f"- **{name}**: {desc}")
            if param_parts:
                tool_lines.extend(param_parts)
            tool_lines.append("")

        sections.append("\n".join(tool_lines))

    # 3. Market context
    if context.market_state is not None:
        ms = context.market_state
        sections.append(
            f"## Current Market Context\n"
            f"Symbol: {ms.symbol}\n"
            f"Regime: {ms.regime.value}\n"
            f"Trend Strength: {ms.trend_strength:.2f}\n"
            f"Volatility: {ms.volatility:.2f}"
        )

    if context.active_symbols:
        sections.append(
            f"## Active Symbols\n"
            f"Currently tracking: {', '.join(context.active_symbols)}"
        )

    # 4. User preferences
    if context.user_preferences:
        pref_lines = ["## User Preferences"]
        for key, value in context.user_preferences.items():
            label = key.replace("_", " ").title()
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value) if value else "none set"
            pref_lines.append(f"- {label}: {value}")
        sections.append("\n".join(pref_lines))

    # 5. Memory context
    if context.memory_context:
        sections.append(
            f"## Relevant Prior Context\n{context.memory_context}"
        )

    # 6. Safety constraints
    sections.append(_SAFETY_PROMPT)

    return "\n\n".join(sections)
