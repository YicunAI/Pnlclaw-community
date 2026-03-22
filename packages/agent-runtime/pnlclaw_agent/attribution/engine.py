"""PnL attribution engine — four-dimensional trade performance analysis.

Decomposes trading PnL into four attribution dimensions:
1. **By strategy** — which strategy contributed what
2. **By period** — weekly/monthly PnL breakdown
3. **By event** — top winning and losing trades
4. **By cost** — commissions, slippage, fees impact

Source: distillation-plan-supplement-3, gap 16.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Attribution result
# ---------------------------------------------------------------------------


@dataclass
class PnLAttribution:
    """Result of four-dimensional PnL attribution.

    Attributes:
        by_strategy: strategy_id → net PnL contribution.
        by_period: period label (e.g. "2025-W12") → net PnL.
        by_event: Top winning/losing trade events with impact.
        by_cost: Cost category (commissions, slippage, fees) → amount.
        total_pnl: Sum of all PnL.
        period_start: Attribution period start (ISO date string).
        period_end: Attribution period end (ISO date string).
    """

    by_strategy: dict[str, float] = field(default_factory=dict)
    by_period: dict[str, float] = field(default_factory=dict)
    by_event: list[dict[str, Any]] = field(default_factory=list)
    by_cost: dict[str, float] = field(default_factory=dict)
    total_pnl: float = 0.0
    period_start: str = ""
    period_end: str = ""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class PnLAttributionEngine:
    """Produces four-dimensional PnL attribution from trade records.

    Trade records are dicts with expected keys:
    - ``strategy_id``: str
    - ``pnl``: float (net PnL of the trade)
    - ``entry_time``: int or str (ms-epoch or ISO datetime)
    - ``exit_time``: int or str
    - ``symbol``: str
    - ``side``: str ("buy" / "sell")
    - ``quantity``: float
    - ``entry_price``: float
    - ``exit_price``: float
    - ``commission``: float (optional, default 0)
    - ``slippage``: float (optional, default 0)
    - ``fees``: float (optional, default 0)
    """

    def explain(
        self,
        trades: list[dict[str, Any]],
        period: tuple[str, str] | None = None,
    ) -> PnLAttribution:
        """Compute four-dimensional PnL attribution.

        Args:
            trades: List of trade record dicts (see class docstring).
            period: Optional (start, end) ISO date strings to filter trades.

        Returns:
            PnLAttribution with all four dimensions populated.
        """
        if not trades:
            return PnLAttribution()

        # Filter by period if specified
        filtered = trades
        if period:
            start_str, end_str = period
            filtered = self._filter_by_period(trades, start_str, end_str)

        # Determine actual period
        p_start, p_end = self._detect_period(filtered, period)

        # 1. By strategy
        by_strategy: dict[str, float] = defaultdict(float)
        for t in filtered:
            sid = t.get("strategy_id", "unknown")
            by_strategy[sid] += t.get("pnl", 0.0)

        # 2. By period (weekly)
        by_period: dict[str, float] = defaultdict(float)
        for t in filtered:
            week_label = self._to_week_label(t)
            by_period[week_label] += t.get("pnl", 0.0)

        # 3. By event (top 3 wins, top 3 losses)
        sorted_trades = sorted(filtered, key=lambda t: t.get("pnl", 0.0))
        top_losses = sorted_trades[:3]
        top_wins = sorted_trades[-3:][::-1]

        by_event: list[dict[str, Any]] = []
        for t in top_wins:
            if t.get("pnl", 0.0) > 0:
                by_event.append({
                    "type": "win",
                    "pnl": t.get("pnl", 0.0),
                    "symbol": t.get("symbol", ""),
                    "side": t.get("side", ""),
                    "time": self._format_time(t.get("exit_time")),
                })
        for t in top_losses:
            if t.get("pnl", 0.0) < 0:
                by_event.append({
                    "type": "loss",
                    "pnl": t.get("pnl", 0.0),
                    "symbol": t.get("symbol", ""),
                    "side": t.get("side", ""),
                    "time": self._format_time(t.get("exit_time")),
                })

        # 4. By cost
        total_commissions = sum(t.get("commission", 0.0) for t in filtered)
        total_slippage = sum(t.get("slippage", 0.0) for t in filtered)
        total_fees = sum(t.get("fees", 0.0) for t in filtered)
        by_cost = {
            "commissions": total_commissions,
            "slippage": total_slippage,
            "fees": total_fees,
        }

        total_pnl = sum(t.get("pnl", 0.0) for t in filtered)

        return PnLAttribution(
            by_strategy=dict(by_strategy),
            by_period=dict(sorted(by_period.items())),
            by_event=by_event,
            by_cost=by_cost,
            total_pnl=total_pnl,
            period_start=p_start,
            period_end=p_end,
        )

    def generate_narrative(self, attribution: PnLAttribution) -> str:
        """Generate a natural-language report from attribution data.

        This is a template-based report, not an LLM call.

        Args:
            attribution: The attribution result from :meth:`explain`.

        Returns:
            A formatted text report string.
        """
        lines: list[str] = []

        # Header
        if attribution.period_start and attribution.period_end:
            lines.append(
                f"PnL Report ({attribution.period_start} to {attribution.period_end})"
            )
        else:
            lines.append("PnL Report")
        lines.append(f"Total PnL: {attribution.total_pnl:+,.2f}")
        lines.append("")

        # By strategy
        if attribution.by_strategy:
            lines.append("By Strategy:")
            for sid, pnl in sorted(attribution.by_strategy.items()):
                lines.append(f"  {sid}: {pnl:+,.2f}")
            lines.append("")

        # By period
        if attribution.by_period:
            lines.append("By Period:")
            for period_label, pnl in attribution.by_period.items():
                lines.append(f"  {period_label}: {pnl:+,.2f}")
            lines.append("")

        # Key events
        if attribution.by_event:
            lines.append("Key Events:")
            for evt in attribution.by_event:
                etype = "Win" if evt["type"] == "win" else "Loss"
                lines.append(
                    f"  {etype}: {evt['pnl']:+,.2f} on {evt['symbol']} "
                    f"({evt['side']}) at {evt.get('time', 'N/A')}"
                )
            lines.append("")

        # Costs
        if attribution.by_cost:
            total_cost = sum(attribution.by_cost.values())
            lines.append("Costs:")
            for cat, amount in attribution.by_cost.items():
                lines.append(f"  {cat.capitalize()}: {amount:,.2f}")
            lines.append(f"  Total costs: {total_cost:,.2f}")

        return "\n".join(lines)

    # -- internal ------------------------------------------------------------

    def _filter_by_period(
        self, trades: list[dict[str, Any]], start: str, end: str
    ) -> list[dict[str, Any]]:
        """Filter trades by date range."""
        try:
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)
        except ValueError:
            return trades  # Can't parse, return all

        result = []
        for t in trades:
            exit_time = t.get("exit_time")
            try:
                if isinstance(exit_time, (int, float)):
                    trade_dt = datetime.fromtimestamp(exit_time / 1000, tz=timezone.utc)
                elif isinstance(exit_time, str):
                    trade_dt = datetime.fromisoformat(exit_time)
                else:
                    result.append(t)
                    continue

                # Make comparison timezone-aware
                if trade_dt.tzinfo is None:
                    trade_dt = trade_dt.replace(tzinfo=timezone.utc)
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)

                if start_dt <= trade_dt <= end_dt:
                    result.append(t)
            except (ValueError, OSError):
                result.append(t)  # Include if can't parse

        return result

    def _detect_period(
        self,
        trades: list[dict[str, Any]],
        explicit: tuple[str, str] | None,
    ) -> tuple[str, str]:
        """Detect or use explicit period boundaries."""
        if explicit:
            return explicit

        if not trades:
            return "", ""

        times: list[float] = []
        for t in trades:
            for key in ("entry_time", "exit_time"):
                val = t.get(key)
                if isinstance(val, (int, float)):
                    times.append(val)

        if not times:
            return "", ""

        min_t = datetime.fromtimestamp(min(times) / 1000, tz=timezone.utc)
        max_t = datetime.fromtimestamp(max(times) / 1000, tz=timezone.utc)
        return min_t.strftime("%Y-%m-%d"), max_t.strftime("%Y-%m-%d")

    def _to_week_label(self, trade: dict[str, Any]) -> str:
        """Get ISO week label for a trade's exit time."""
        exit_time = trade.get("exit_time")
        try:
            if isinstance(exit_time, (int, float)):
                dt = datetime.fromtimestamp(exit_time / 1000, tz=timezone.utc)
            elif isinstance(exit_time, str):
                dt = datetime.fromisoformat(exit_time)
            else:
                return "unknown"
            iso = dt.isocalendar()
            return f"{iso[0]}-W{iso[1]:02d}"
        except (ValueError, OSError):
            return "unknown"

    def _format_time(self, val: Any) -> str:
        """Format a timestamp for display."""
        try:
            if isinstance(val, (int, float)):
                dt = datetime.fromtimestamp(val / 1000, tz=timezone.utc)
                return dt.strftime("%Y-%m-%d %H:%M")
            if isinstance(val, str):
                return val[:16]
        except (ValueError, OSError):
            pass
        return "N/A"
