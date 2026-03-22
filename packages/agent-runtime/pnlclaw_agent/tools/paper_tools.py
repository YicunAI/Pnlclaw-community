"""Paper trading tools — account creation, order placement, positions, PnL.

Tools wrap ``AccountManager``, ``PaperOrderManager``, and ``PositionManager``
from the paper-engine package.
"""

from __future__ import annotations

from typing import Any

from pnlclaw_types.risk import RiskLevel
from pnlclaw_types.trading import OrderSide, OrderType

from pnlclaw_agent.tools.base import BaseTool, ToolResult


# ---------------------------------------------------------------------------
# Enum mapping helpers
# ---------------------------------------------------------------------------

_SIDE_MAP: dict[str, OrderSide] = {
    "buy": OrderSide.BUY,
    "sell": OrderSide.SELL,
}

_TYPE_MAP: dict[str, OrderType] = {
    "market": OrderType.MARKET,
    "limit": OrderType.LIMIT,
    "stop_market": OrderType.STOP_MARKET,
    "stop_limit": OrderType.STOP_LIMIT,
}


# ---------------------------------------------------------------------------
# PaperCreateAccountTool
# ---------------------------------------------------------------------------


class PaperCreateAccountTool(BaseTool):
    """Create a new paper trading account with an initial balance."""

    def __init__(self, account_manager: Any) -> None:
        self._manager = account_manager

    @property
    def name(self) -> str:
        return "paper_create_account"

    @property
    def description(self) -> str:
        return (
            "Create a new paper trading account with a specified name "
            "and initial balance for simulated trading."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Account name"},
                "initial_balance": {
                    "type": "number",
                    "description": "Starting balance in quote currency (e.g. USDT)",
                },
            },
            "required": ["name", "initial_balance"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.RESTRICTED

    def execute(self, args: dict[str, Any]) -> ToolResult:
        acct_name = args.get("name", "")
        balance = args.get("initial_balance")

        if not acct_name:
            return ToolResult(output="", error="Missing required parameter: name")
        if balance is None or not isinstance(balance, (int, float)) or balance <= 0:
            return ToolResult(output="", error="initial_balance must be a positive number")

        try:
            account = self._manager.create_account(acct_name, float(balance))
        except Exception as exc:
            return ToolResult(output=f"Account creation failed: {exc}", error=str(exc))

        return ToolResult(
            output=(
                f"Paper account created successfully.\n"
                f"  ID: {account.id}\n"
                f"  Name: {account.name}\n"
                f"  Balance: {account.current_balance:,.2f}\n"
                f"  Status: {account.status.value}"
            )
        )


# ---------------------------------------------------------------------------
# PaperPlaceOrderTool
# ---------------------------------------------------------------------------


class PaperPlaceOrderTool(BaseTool):
    """Place a simulated order on a paper trading account."""

    def __init__(self, order_manager: Any) -> None:
        self._manager = order_manager

    @property
    def name(self) -> str:
        return "paper_place_order"

    @property
    def description(self) -> str:
        return (
            "Place a simulated order (buy/sell, market/limit) on a paper "
            "trading account."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "account_id": {"type": "string", "description": "Paper account ID"},
                "symbol": {"type": "string", "description": "Trading pair, e.g. 'BTC/USDT'"},
                "side": {"type": "string", "description": "'buy' or 'sell'"},
                "order_type": {"type": "string", "description": "'market' or 'limit'"},
                "quantity": {"type": "number", "description": "Order quantity in base currency"},
                "price": {"type": "number", "description": "Limit price (required for limit orders)"},
                "stop_price": {"type": "number", "description": "Stop trigger price (optional)"},
            },
            "required": ["account_id", "symbol", "side", "order_type", "quantity"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.RESTRICTED

    def execute(self, args: dict[str, Any]) -> ToolResult:
        account_id = args.get("account_id", "")
        symbol = args.get("symbol", "")
        side_str = args.get("side", "").lower()
        type_str = args.get("order_type", "").lower()
        quantity = args.get("quantity")

        if not account_id:
            return ToolResult(output="", error="Missing required parameter: account_id")
        if not symbol:
            return ToolResult(output="", error="Missing required parameter: symbol")

        side = _SIDE_MAP.get(side_str)
        if side is None:
            return ToolResult(output="", error=f"Invalid side '{side_str}'. Use 'buy' or 'sell'.")

        order_type = _TYPE_MAP.get(type_str)
        if order_type is None:
            return ToolResult(
                output="",
                error=f"Invalid order_type '{type_str}'. Use 'market' or 'limit'.",
            )

        if not isinstance(quantity, (int, float)) or quantity <= 0:
            return ToolResult(output="", error="quantity must be a positive number")

        try:
            order = self._manager.place_order(
                account_id,
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=float(quantity),
                price=args.get("price"),
                stop_price=args.get("stop_price"),
            )
        except Exception as exc:
            return ToolResult(output=f"Order placement failed: {exc}", error=str(exc))

        price_info = f"  Price: {order.price}" if order.price else ""
        return ToolResult(
            output=(
                f"Order placed successfully.\n"
                f"  Order ID: {order.id}\n"
                f"  Symbol: {order.symbol}\n"
                f"  Side: {order.side.value} | Type: {order.type.value}\n"
                f"  Quantity: {order.quantity}\n"
                f"  Status: {order.status.value}"
                f"{price_info}"
            )
        )


# ---------------------------------------------------------------------------
# PaperPositionsTool
# ---------------------------------------------------------------------------


class PaperPositionsTool(BaseTool):
    """View current positions for a paper trading account."""

    def __init__(self, position_manager: Any) -> None:
        self._manager = position_manager

    @property
    def name(self) -> str:
        return "paper_positions"

    @property
    def description(self) -> str:
        return "List all open positions for a paper trading account."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "account_id": {"type": "string", "description": "Paper account ID"},
            },
            "required": ["account_id"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.SAFE

    def execute(self, args: dict[str, Any]) -> ToolResult:
        account_id = args.get("account_id", "")
        if not account_id:
            return ToolResult(output="", error="Missing required parameter: account_id")

        positions = self._manager.get_positions(account_id)
        if not positions:
            return ToolResult(output=f"No positions found for account {account_id}")

        lines = [f"Positions for account {account_id}:", ""]
        for pos in positions:
            status = "open" if pos.quantity > 0 else "closed"
            lines.append(
                f"  {pos.symbol} | {pos.side.value} | Qty: {pos.quantity:.4f} "
                f"| Avg Entry: {pos.avg_entry_price:.2f} "
                f"| Unrealized PnL: {pos.unrealized_pnl:+.2f} "
                f"| Realized PnL: {pos.realized_pnl:+.2f} "
                f"| ({status})"
            )
        return ToolResult(output="\n".join(lines))


# ---------------------------------------------------------------------------
# PaperPnlTool
# ---------------------------------------------------------------------------


class PaperPnlTool(BaseTool):
    """View profit/loss summary for a paper trading account."""

    def __init__(self, position_manager: Any, market_service: Any) -> None:
        self._position_manager = position_manager
        self._market_service = market_service

    @property
    def name(self) -> str:
        return "paper_pnl"

    @property
    def description(self) -> str:
        return (
            "Calculate and display the profit/loss summary for a paper "
            "trading account, including realized and unrealized PnL."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "account_id": {"type": "string", "description": "Paper account ID"},
            },
            "required": ["account_id"],
        }

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.SAFE

    def execute(self, args: dict[str, Any]) -> ToolResult:
        account_id = args.get("account_id", "")
        if not account_id:
            return ToolResult(output="", error="Missing required parameter: account_id")

        positions = self._position_manager.get_positions(account_id)
        if not positions:
            return ToolResult(output=f"No positions found for account {account_id}")

        # Get current prices for each symbol
        prices: dict[str, float] = {}
        for pos in positions:
            if pos.quantity > 0 and pos.symbol not in prices:
                ticker = self._market_service.get_ticker(pos.symbol)
                if ticker:
                    prices[pos.symbol] = ticker.last_price

        from pnlclaw_paper.pnl import calculate_account_pnl
        pnl_records = calculate_account_pnl(positions, prices)

        total_realized = sum(r.realized_pnl for r in pnl_records)
        total_unrealized = sum(r.unrealized_pnl for r in pnl_records)
        total_fees = sum(r.fees for r in pnl_records)
        total_pnl = total_realized + total_unrealized

        lines = [
            f"PnL Summary for account {account_id}",
            "",
            f"  Total PnL: {total_pnl:+,.2f}",
            f"  Realized: {total_realized:+,.2f}",
            f"  Unrealized: {total_unrealized:+,.2f}",
            f"  Fees: {total_fees:,.2f}",
            "",
            "  By Symbol:",
        ]
        for record in pnl_records:
            lines.append(
                f"    {record.symbol}: "
                f"realized {record.realized_pnl:+,.2f} | "
                f"unrealized {record.unrealized_pnl:+,.2f} | "
                f"total {record.total_pnl:+,.2f}"
            )
        return ToolResult(output="\n".join(lines))
