"""Agent role definitions — v0.1 multi-agent simulation via system prompts.

In v0.1 multi-agent behavior is simulated by switching the system prompt
and restricting the available tool set per role.  True multi-process
agents are planned for v0.2.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass

from pnlclaw_types.agent import AgentRole


@dataclass(frozen=True)
class RoleDefinition:
    """Definition of an agent role.

    Attributes:
        name: Human-readable role name.
        system_prompt: Role-specific system prompt for the LLM.
        allowed_tools: Tool names this role is permitted to use.
        description: Short description of the role's purpose.
    """

    name: str
    system_prompt: str
    allowed_tools: list[str]
    description: str


# ---------------------------------------------------------------------------
# Role definitions
# ---------------------------------------------------------------------------

AGENT_ROLES: dict[str, RoleDefinition] = {
    "market_analyst": RoleDefinition(
        name="Market Analyst",
        system_prompt=textwrap.dedent("""\
            You are a Market Analyst specializing in crypto markets.
            Your job is to analyze price action, order book depth, and market regime.
            Provide data-driven observations based on real data — not speculation.

            Always use market tools to fetch real-time data before drawing conclusions.
            Focus on objective analysis: trend direction, volatility level, market regime,
            and key support/resistance levels.

            You do NOT give trading advice or make buy/sell recommendations.
            You provide market intelligence that other agents use for decision-making.
        """),
        allowed_tools=[
            "market_ticker",
            "market_kline",
            "market_orderbook",
            "explain_market",
        ],
        description="Analyzes market data, identifies regimes, and provides market intelligence.",
    ),
    "strategy_architect": RoleDefinition(
        name="Strategy Architect",
        system_prompt=textwrap.dedent("""\
            You are a Strategy Architect who designs, validates, and backtests
            quantitative trading strategies.

            Help users define entry/exit rules using technical indicators,
            validate strategy configurations for correctness, and interpret
            backtest results with actionable insights.

            When designing strategies, consider:
            - Market regime suitability (trend-following vs mean-reversion)
            - Risk management parameters (stop-loss, position sizing)
            - Parameter sensitivity and overfitting risk

            Always validate strategies before backtesting.
            Always use backtesting data to support or refute strategy hypotheses.
        """),
        allowed_tools=[
            "strategy_validate",
            "backtest_run",
            "backtest_result",
            "market_ticker",
            "market_kline",
        ],
        description="Designs, validates, and backtests quantitative trading strategies.",
    ),
    "risk_guardian": RoleDefinition(
        name="Risk Guardian",
        system_prompt=textwrap.dedent("""\
            You are a Risk Guardian responsible for evaluating trade safety
            and protecting capital.

            Your priorities (in order):
            1. Capital preservation — never allow unacceptable risk
            2. Risk-adjusted returns — prefer trades with favorable risk/reward
            3. Consistency — flag erratic trading patterns

            Check every trade intent against risk rules. Monitor position sizes.
            Explain PnL attribution to help users understand performance drivers.

            When you identify a risk concern, be direct and specific.
            Do NOT approve trades that violate risk rules, even if the user insists.
        """),
        allowed_tools=[
            "risk_check",
            "risk_report",
            "paper_positions",
            "paper_pnl",
            "explain_pnl",
        ],
        description="Evaluates trade safety, monitors risk, and explains PnL attribution.",
    ),
}


def get_role(role: AgentRole) -> RoleDefinition:
    """Look up a role definition by AgentRole enum.

    Args:
        role: The agent role to look up.

    Returns:
        The matching RoleDefinition.

    Raises:
        KeyError: If the role is not defined.
    """
    key = role.value.lower()
    if key not in AGENT_ROLES:
        raise KeyError(f"Unknown agent role: {role.value}")
    return AGENT_ROLES[key]
