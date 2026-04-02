"""Explain tools — PnL explanation and market state explanation.

These tools format analytical insights for the LLM, bridging
paper-engine PnL calculations and market-data state analysis.
"""

from __future__ import annotations

from typing import Any

from pnlclaw_agent.tools.base import BaseTool, ToolResult
from pnlclaw_types.market import KlineEvent
from pnlclaw_types.risk import RiskLevel

# ---------------------------------------------------------------------------
# ExplainPnlTool
# ---------------------------------------------------------------------------


class ExplainPnlTool(BaseTool):
    """Explain the profit/loss composition for a paper trading account."""

    def __init__(self, position_manager: Any, market_service: Any) -> None:
        self._position_manager = position_manager
        self._market_service = market_service

    @property
    def name(self) -> str:
        return "explain_pnl"

    @property
    def description(self) -> str:
        return (
            "Explain the PnL composition for a paper trading account, "
            "decomposing into realized vs unrealized gains, fees, "
            "and per-symbol breakdown."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "account_id": {"type": "string", "description": "Paper account ID"},
                "symbol": {
                    "type": "string",
                    "description": "Optional: filter to a specific symbol",
                },
            },
            "required": ["account_id"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.SAFE

    def execute(self, args: dict[str, Any]) -> ToolResult:
        account_id = args.get("account_id", "")
        symbol_filter = args.get("symbol")

        if not account_id:
            return ToolResult(output="", error="Missing required parameter: account_id")

        positions = self._position_manager.get_positions(account_id)
        if symbol_filter:
            positions = [p for p in positions if p.symbol == symbol_filter]

        if not positions:
            target = f" for {symbol_filter}" if symbol_filter else ""
            return ToolResult(output=f"No positions found{target} in account {account_id}")

        # Get current prices and calculate PnL
        from pnlclaw_paper.pnl import calculate_pnl

        lines = [f"PnL Explanation for account {account_id}", ""]
        total_realized = 0.0
        total_unrealized = 0.0

        for pos in positions:
            current_price = None
            ticker = self._market_service.get_ticker(pos.symbol)
            if ticker:
                current_price = ticker.last_price

            if current_price and pos.quantity > 0:
                record = calculate_pnl(pos, current_price)
                total_realized += record.realized_pnl
                total_unrealized += record.unrealized_pnl

                lines.append(f"  {pos.symbol} ({pos.side.value}):")
                lines.append(f"    Entry Price: {pos.avg_entry_price:.2f}")
                lines.append(f"    Current Price: {current_price:.2f}")
                lines.append(f"    Quantity: {pos.quantity:.4f}")

                if pos.side.value == "buy":
                    direction = "Long"
                    pct = ((current_price - pos.avg_entry_price) / pos.avg_entry_price) * 100
                else:
                    direction = "Short"
                    pct = ((pos.avg_entry_price - current_price) / pos.avg_entry_price) * 100

                lines.append(f"    Direction: {direction}")
                lines.append(f"    Unrealized PnL: {record.unrealized_pnl:+,.2f} ({pct:+.2f}%)")
                lines.append(f"    Realized PnL: {record.realized_pnl:+,.2f}")
                lines.append("")
            elif pos.quantity == 0:
                total_realized += pos.realized_pnl
                lines.append(f"  {pos.symbol} (closed):")
                lines.append(f"    Realized PnL: {pos.realized_pnl:+,.2f}")
                lines.append("")

        lines.append("  Summary:")
        lines.append(f"    Total Realized: {total_realized:+,.2f}")
        lines.append(f"    Total Unrealized: {total_unrealized:+,.2f}")
        lines.append(f"    Net PnL: {total_realized + total_unrealized:+,.2f}")

        return ToolResult(output="\n".join(lines))


# ---------------------------------------------------------------------------
# ExplainMarketTool
# ---------------------------------------------------------------------------


class ExplainMarketTool(BaseTool):
    """Explain the current market state for a trading pair."""

    def __init__(self, state_engine: Any, market_service: Any) -> None:
        self._state_engine = state_engine
        self._market_service = market_service

    @property
    def name(self) -> str:
        return "explain_market"

    @property
    def description(self) -> str:
        return (
            "Analyze and explain the current market state for a trading pair, "
            "including market regime (trending/ranging/volatile), trend strength, "
            "and volatility level."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Trading pair, e.g. 'BTC/USDT'",
                },
                "klines": {
                    "type": "array",
                    "description": (
                        "Optional: list of kline dicts with keys: "
                        "exchange, symbol, timestamp, interval, open, high, "
                        "low, close, volume, closed"
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "exchange": {"type": "string"},
                            "symbol": {"type": "string"},
                            "timestamp": {"type": "number"},
                            "interval": {"type": "string"},
                            "open": {"type": "number"},
                            "high": {"type": "number"},
                            "low": {"type": "number"},
                            "close": {"type": "number"},
                            "volume": {"type": "number"},
                            "closed": {"type": "boolean"},
                        },
                    },
                },
            },
            "required": ["symbol"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.SAFE

    def execute(self, args: dict[str, Any]) -> ToolResult:
        symbol = args.get("symbol", "")
        if not symbol:
            return ToolResult(output="", error="Missing required parameter: symbol")

        klines_data = args.get("klines")

        if klines_data and isinstance(klines_data, list):
            try:
                klines = [KlineEvent.model_validate(k) for k in klines_data]
            except Exception as exc:
                return ToolResult(
                    output=f"Failed to parse kline data: {exc}",
                    error="Invalid kline data",
                )
        else:
            # No klines provided — cannot perform analysis
            return ToolResult(
                output=(
                    f"Cannot analyze market state for {symbol} without "
                    f"historical kline data. Please provide kline data via "
                    f"the 'klines' parameter (at least 15 bars recommended)."
                )
            )

        if len(klines) < 5:
            return ToolResult(output="Need at least 5 kline bars for market state analysis.")

        try:
            state = self._state_engine.analyze(symbol, klines)
        except Exception as exc:
            return ToolResult(output=f"Market analysis failed: {exc}", error=str(exc))

        # Interpret the state
        regime_desc = {
            "trending": "The market is in a clear trend",
            "ranging": "The market is range-bound / consolidating",
            "volatile": "The market is experiencing high volatility",
        }
        regime_text = regime_desc.get(state.regime.value, state.regime.value)

        trend_label = "weak" if state.trend_strength < 0.3 else ("moderate" if state.trend_strength < 0.7 else "strong")
        vol_label = "low" if state.volatility < 0.3 else ("moderate" if state.volatility < 0.7 else "high")

        lines = [
            f"Market State Analysis — {symbol}",
            "",
            f"  Regime: {state.regime.value.capitalize()}",
            f"    {regime_text}",
            f"  Trend Strength: {state.trend_strength:.2f} ({trend_label})",
            f"  Volatility: {state.volatility:.2f} ({vol_label})",
            "",
            "  Implications:",
        ]

        if state.regime.value == "trending":
            lines.append("    - Trend-following strategies may be effective")
            lines.append("    - Mean-reversion strategies may underperform")
        elif state.regime.value == "ranging":
            lines.append("    - Mean-reversion strategies may be effective")
            lines.append("    - Trend-following strategies may generate false signals")
        else:
            lines.append("    - Use caution — volatile markets increase risk")
            lines.append("    - Consider reducing position sizes")

        return ToolResult(output="\n".join(lines))
