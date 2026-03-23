"""Tests for paper trading tools."""

from __future__ import annotations

from dataclasses import dataclass, field

from pnlclaw_agent.tools.paper_tools import (
    PaperCreateAccountTool,
    PaperPlaceOrderTool,
    PaperPnlTool,
    PaperPositionsTool,
)
from pnlclaw_paper.accounts import AccountManager
from pnlclaw_paper.orders import PaperOrderManager
from pnlclaw_paper.positions import PositionManager
from pnlclaw_types.market import TickerEvent
from pnlclaw_types.trading import Fill, OrderSide

# ---------------------------------------------------------------------------
# Mock MarketDataService (for PnL)
# ---------------------------------------------------------------------------


@dataclass
class MockMarketService:
    tickers: dict[str, TickerEvent] = field(default_factory=dict)

    def get_ticker(self, symbol: str) -> TickerEvent | None:
        return self.tickers.get(symbol)


_NOW = 1_700_000_000_000


# ---------------------------------------------------------------------------
# PaperCreateAccountTool tests
# ---------------------------------------------------------------------------


class TestPaperCreateAccountTool:
    def test_create_account(self) -> None:
        manager = AccountManager()
        tool = PaperCreateAccountTool(manager)
        result = tool.execute({"name": "Test Account", "initial_balance": 10000})
        assert result.error is None
        assert "Test Account" in result.output
        assert "10,000.00" in result.output

    def test_missing_name(self) -> None:
        tool = PaperCreateAccountTool(AccountManager())
        result = tool.execute({"initial_balance": 10000})
        assert result.error is not None

    def test_invalid_balance(self) -> None:
        tool = PaperCreateAccountTool(AccountManager())
        result = tool.execute({"name": "Bad", "initial_balance": -100})
        assert result.error is not None


# ---------------------------------------------------------------------------
# PaperPlaceOrderTool tests
# ---------------------------------------------------------------------------


class TestPaperPlaceOrderTool:
    def test_place_market_order(self) -> None:
        manager = PaperOrderManager()
        tool = PaperPlaceOrderTool(manager)
        result = tool.execute(
            {
                "account_id": "acct-1",
                "symbol": "BTC/USDT",
                "side": "buy",
                "order_type": "market",
                "quantity": 0.5,
            }
        )
        assert result.error is None
        assert "BTC/USDT" in result.output
        assert "buy" in result.output.lower()

    def test_invalid_side(self) -> None:
        tool = PaperPlaceOrderTool(PaperOrderManager())
        result = tool.execute(
            {
                "account_id": "acct-1",
                "symbol": "BTC/USDT",
                "side": "invalid",
                "order_type": "market",
                "quantity": 1.0,
            }
        )
        assert result.error is not None
        assert "side" in result.error.lower()

    def test_invalid_order_type(self) -> None:
        tool = PaperPlaceOrderTool(PaperOrderManager())
        result = tool.execute(
            {
                "account_id": "acct-1",
                "symbol": "BTC/USDT",
                "side": "buy",
                "order_type": "weird",
                "quantity": 1.0,
            }
        )
        assert result.error is not None

    def test_missing_required_fields(self) -> None:
        tool = PaperPlaceOrderTool(PaperOrderManager())
        result = tool.execute({"account_id": "acct-1"})
        assert result.error is not None


# ---------------------------------------------------------------------------
# PaperPositionsTool tests
# ---------------------------------------------------------------------------


class TestPaperPositionsTool:
    def test_no_positions(self) -> None:
        pm = PositionManager()
        tool = PaperPositionsTool(pm)
        result = tool.execute({"account_id": "acct-1"})
        assert "No positions found" in result.output

    def test_with_positions(self) -> None:
        pm = PositionManager()
        fill = Fill(id="f1", order_id="o1", price=67000.0, quantity=1.0, timestamp=_NOW)
        pm.apply_fill_with_symbol("acct-1", "BTC/USDT", fill, OrderSide.BUY)

        tool = PaperPositionsTool(pm)
        result = tool.execute({"account_id": "acct-1"})
        assert result.error is None
        assert "BTC/USDT" in result.output
        assert "buy" in result.output.lower()

    def test_missing_account_id(self) -> None:
        tool = PaperPositionsTool(PositionManager())
        result = tool.execute({})
        assert result.error is not None


# ---------------------------------------------------------------------------
# PaperPnlTool tests
# ---------------------------------------------------------------------------


class TestPaperPnlTool:
    def test_pnl_with_position(self) -> None:
        pm = PositionManager()
        fill = Fill(id="f1", order_id="o1", price=60000.0, quantity=1.0, timestamp=_NOW)
        pm.apply_fill_with_symbol("acct-1", "BTC/USDT", fill, OrderSide.BUY)

        market = MockMarketService(
            tickers={
                "BTC/USDT": TickerEvent(
                    exchange="binance",
                    symbol="BTC/USDT",
                    timestamp=_NOW,
                    last_price=65000.0,
                    bid=64999.0,
                    ask=65001.0,
                    volume_24h=1000.0,
                    change_24h_pct=1.0,
                ),
            }
        )
        tool = PaperPnlTool(pm, market)
        result = tool.execute({"account_id": "acct-1"})
        assert result.error is None
        assert "BTC/USDT" in result.output

    def test_no_positions(self) -> None:
        tool = PaperPnlTool(PositionManager(), MockMarketService())
        result = tool.execute({"account_id": "acct-1"})
        assert "No positions found" in result.output
