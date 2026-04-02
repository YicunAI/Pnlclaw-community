"""Server-side analysis prompt templates.

All analysis prompt templates are maintained here so that no prompt
engineering logic is exposed in the frontend JavaScript bundle.
The frontend sends only a structured intent + data; this module
assembles the full LLM prompt.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Intent constants
# ---------------------------------------------------------------------------

INTENT_MULTI_TIMEFRAME = "multi_timeframe_analysis"
INTENT_TIMEFRAME_TRADE = "timeframe_trade"
INTENT_CLOSE_EVALUATION = "close_evaluation"
INTENT_BACKTEST_EXPLAIN = "backtest_explain"

VALID_INTENTS = frozenset(
    {
        INTENT_MULTI_TIMEFRAME,
        INTENT_TIMEFRAME_TRADE,
        INTENT_CLOSE_EVALUATION,
        INTENT_BACKTEST_EXPLAIN,
    }
)


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_MULTI_TIMEFRAME = """\
[Current view: symbol={symbol}, exchange={exchange}, market_type={market_type}, timeframe=15m, 1h, 4h]
{position_block}分析当前 {base}/USDT 永续合约的行情走势。当前标记价格 {mark_price}。
{position_block_dup}请给出：
1) 15分钟(超短线)、1小时(短线)、4小时(中线) 三个关键周期的趋势和关键支撑/阻力位。
2) 如果我有持仓，请给出针对持仓的建议（如加仓、减仓、平仓、调整止损等）。如果没有，请给出整体仓位配比建议。
最后，请询问我想做哪个周期，以便提供更精确的具体点位。"""

_TIMEFRAME_TRADE = """\
[Current view: symbol={symbol}, exchange={exchange}, market_type={market_type}, timeframe={timeframe}]
{position_block}我现在想做 {timeframe} 级别的交易。请基于当前标记价格 {mark_price}，\
{position_ref}给出**严格对应 {timeframe} 级别**的具体操作建议（包括入场点位、止盈止损点位、仓位配比）。请简洁回答。"""

_CLOSE_EVAL_WITH_POS = """\
[Current view: symbol={symbol}, exchange={exchange}, market_type={market_type}, timeframe=15m, 1h, 4h]
{position_block}
我想评估当前持仓是否应该平仓。请基于当前标记价格 {mark_price}，结合我的持仓情况，给出以下分析：
1) 当前持仓的盈亏状态和风险评估
2) 是否建议平仓（全部或部分），以及理由
3) 如果建议继续持有，给出调整止损/止盈的建议点位
4) 如果建议平仓，给出具体的平仓方案（含具体点位/数量/杠杆）
请简洁回答。"""

_CLOSE_EVAL_NO_POS = """\
[Current view: symbol={symbol}, exchange={exchange}, market_type={market_type}, timeframe=15m, 1h, 4h]
当前没有找到活跃持仓数据。请基于当前标记价格 {mark_price}，\
分析 {base}/USDT 永续合约的短线走势，并给出新开仓的入场建议（方向、点位、止盈止损、仓位配比）。请简洁回答。"""

_BACKTEST_EXPLAIN = """\
[Backtest explanation request]
策略: {strategy_name} ({strategy_id})
回测ID: {backtest_id}
交易对: {symbol}
周期: {timeframe}

关键指标:
- 总收益: {total_return:.2%}
- 年化收益: {annual_return:.2%}
- Sharpe: {sharpe_ratio:.2f}
- 最大回撤: {max_drawdown:.2%}
- 胜率: {win_rate:.2%}
- Profit Factor: {profit_factor:.2f}
- 总交易数: {total_trades}
- Calmar: {calmar_ratio:.2f}
- Sortino: {sortino_ratio:.2f}
- Expectancy: {expectancy:.2f}
- Recovery Factor: {recovery_factor:.2f}

请用通俗中文解释：
1) 这次回测整体表现如何；
2) 收益、回撤、Sharpe、胜率、交易次数分别说明了什么；
3) 这个策略最值得警惕的风险点；
4) 下一步应该优先优化什么。
请避免空泛结论，直接基于这些指标回答。"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _derive_base(symbol: str) -> str:
    """Extract the base currency from a symbol string."""
    if "/" in symbol:
        return symbol.split("/")[0]
    return symbol.split("-")[0]


def _format_position_block(
    positions: list[dict[str, Any]],
    contract_symbol: str,
    base: str,
) -> str:
    """Build the position context block from structured position data."""
    if not positions:
        return ""
    lines = ["【用户当前持仓状态】"]
    for p in positions:
        pos_side = p.get("pos_side") or p.get("side", "long")
        side_label = "多单" if pos_side in ("long", "buy") else "空单"
        leverage = p.get("leverage", 1)
        margin = _safe_float(p.get("margin", 0))
        qty_base = _safe_float(p.get("quantity_base", 0))
        avg_entry = _safe_float(p.get("avg_entry_price") or p.get("entry_price", 0))
        unrealized = _safe_float(p.get("unrealized_pnl", 0))
        lines.append(
            f"- {contract_symbol} {side_label}: "
            f"杠杆 {leverage}x, "
            f"占用保证金 {margin:.2f} USDT, "
            f"数量 {qty_base:.4f} {base}, "
            f"开仓均价 {avg_entry:.2f} USDT, "
            f"未实现盈亏 {unrealized:.2f} USDT"
        )
    return "\n".join(lines) + "\n"


def _safe_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_analysis_prompt(context: dict[str, Any]) -> str | None:
    """Build an analysis prompt from a structured frontend context.

    Returns the assembled prompt string, or ``None`` when the context
    does not contain a recognised ``intent``.
    """
    intent = context.get("intent")
    if intent not in VALID_INTENTS:
        return None

    symbol = context.get("symbol", "BTC/USDT")
    exchange = context.get("exchange", "okx")
    market_type = context.get("market_type", "futures")
    timeframe = context.get("timeframe", "1h")
    mark_price = context.get("mark_price", "未知")
    positions: list[dict[str, Any]] = context.get("positions") or []
    contract_symbol = context.get("contract_symbol", symbol)

    base = _derive_base(symbol)
    pos_block = _format_position_block(positions, contract_symbol, base)

    if intent == INTENT_MULTI_TIMEFRAME:
        return _MULTI_TIMEFRAME.format(
            symbol=symbol,
            exchange=exchange,
            market_type=market_type,
            base=base,
            mark_price=mark_price,
            position_block=pos_block,
            position_block_dup=pos_block,
        )

    if intent == INTENT_TIMEFRAME_TRADE:
        position_ref = "结合我的持仓情况，" if pos_block else ""
        return _TIMEFRAME_TRADE.format(
            symbol=symbol,
            exchange=exchange,
            market_type=market_type,
            timeframe=timeframe,
            mark_price=mark_price,
            position_block=pos_block,
            position_ref=position_ref,
        )

    if intent == INTENT_CLOSE_EVALUATION:
        if positions:
            return _CLOSE_EVAL_WITH_POS.format(
                symbol=symbol,
                exchange=exchange,
                market_type=market_type,
                mark_price=mark_price,
                position_block=pos_block,
            )
        return _CLOSE_EVAL_NO_POS.format(
            symbol=symbol,
            exchange=exchange,
            market_type=market_type,
            mark_price=mark_price,
            base=base,
        )

    if intent == INTENT_BACKTEST_EXPLAIN:
        metrics = context.get("metrics") or {}
        return _BACKTEST_EXPLAIN.format(
            backtest_id=context.get("backtest_id", "unknown"),
            strategy_id=context.get("strategy_id", "unknown"),
            strategy_name=context.get("strategy_name", "unknown strategy"),
            symbol=context.get("symbol", "BTC/USDT"),
            timeframe=context.get("timeframe", "1h"),
            total_return=_safe_float(metrics.get("total_return", 0.0)),
            annual_return=_safe_float(metrics.get("annual_return", 0.0)),
            sharpe_ratio=_safe_float(metrics.get("sharpe_ratio", 0.0)),
            max_drawdown=_safe_float(metrics.get("max_drawdown", 0.0)),
            win_rate=_safe_float(metrics.get("win_rate", 0.0)),
            profit_factor=_safe_float(metrics.get("profit_factor", 0.0)),
            total_trades=int(_safe_float(metrics.get("total_trades", 0))),
            calmar_ratio=_safe_float(metrics.get("calmar_ratio", 0.0)),
            sortino_ratio=_safe_float(metrics.get("sortino_ratio", 0.0)),
            expectancy=_safe_float(metrics.get("expectancy", 0.0)),
            recovery_factor=_safe_float(metrics.get("recovery_factor", 0.0)),
        )

    return None
