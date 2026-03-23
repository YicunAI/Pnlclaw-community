"""Tests for unified trading adapters (Binance, OKX, Polymarket)."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from pnlclaw_types.trading import OrderSide, OrderStatus, OrderType

from pnlclaw_exchange.trading import (
    BalanceInfo,
    BinanceTradingAdapter,
    OKXTradingAdapter,
    OrderRequest,
    OrderResponse,
    PolymarketTradingAdapter,
    TradingClient,
)


# ---------------------------------------------------------------------------
# OrderRequest model
# ---------------------------------------------------------------------------


class TestOrderRequest:
    def test_creation(self) -> None:
        req = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.001,
            price=60000.0,
        )
        assert req.symbol == "BTC/USDT"
        assert req.time_in_force == "GTC"

    def test_market_order_no_price(self) -> None:
        req = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=0.5,
        )
        assert req.price is None

    def test_serialization(self) -> None:
        req = OrderRequest(
            symbol="ETH/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=3500.0,
        )
        data = req.model_dump()
        assert data["symbol"] == "ETH/USDT"
        assert data["order_type"] == "limit"


# ---------------------------------------------------------------------------
# BinanceTradingAdapter
# ---------------------------------------------------------------------------


class TestBinanceTradingAdapter:
    def _make_adapter(self) -> tuple[BinanceTradingAdapter, AsyncMock]:
        mock_client = AsyncMock()
        adapter = BinanceTradingAdapter(mock_client)
        return adapter, mock_client

    @pytest.mark.asyncio
    async def test_place_order(self) -> None:
        adapter, mock = self._make_adapter()
        mock.place_order.return_value = {
            "orderId": 12345,
            "clientOrderId": "test-id",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "LIMIT",
            "status": "NEW",
            "origQty": "0.001",
            "executedQty": "0.0",
            "cummulativeQuoteQty": "0.0",
            "price": "60000.00",
            "transactTime": 1711000000000,
        }

        req = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.001,
            price=60000.0,
        )
        result = await adapter.place_order(req)

        assert result.exchange == "binance"
        assert result.order_id == "12345"
        assert result.status == OrderStatus.ACCEPTED
        assert result.quantity == 0.001
        mock.place_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_order(self) -> None:
        adapter, mock = self._make_adapter()
        mock.cancel_order.return_value = {
            "orderId": 12345,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "LIMIT",
            "status": "CANCELED",
            "origQty": "0.001",
            "executedQty": "0.0",
            "cummulativeQuoteQty": "0.0",
            "price": "60000.00",
        }
        result = await adapter.cancel_order(symbol="BTC/USDT", order_id="12345")
        assert result.status == OrderStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_get_balances(self) -> None:
        adapter, mock = self._make_adapter()
        mock.get_balances.return_value = [
            {"asset": "BTC", "free": "0.5", "locked": "0.1"},
            {"asset": "USDT", "free": "10000", "locked": "0"},
        ]
        balances = await adapter.get_balances()
        assert len(balances) == 2
        assert balances[0].asset == "BTC"
        assert balances[0].free == 0.5
        assert balances[0].total == 0.6

    @pytest.mark.asyncio
    async def test_exchange_name(self) -> None:
        adapter, _ = self._make_adapter()
        assert adapter.exchange_name == "binance"

    def test_parse_filled_order(self) -> None:
        adapter, _ = self._make_adapter()
        result = adapter._parse_order_response({
            "orderId": 99,
            "symbol": "ETHUSDT",
            "side": "SELL",
            "type": "MARKET",
            "status": "FILLED",
            "origQty": "1.0",
            "executedQty": "1.0",
            "cummulativeQuoteQty": "3500.0",
            "price": "0.00",
            "transactTime": 1711000000000,
        })
        assert result.status == OrderStatus.FILLED
        assert result.filled_quantity == 1.0
        assert result.avg_fill_price == 3500.0


# ---------------------------------------------------------------------------
# OKXTradingAdapter
# ---------------------------------------------------------------------------


class TestOKXTradingAdapter:
    def _make_adapter(self) -> tuple[OKXTradingAdapter, AsyncMock]:
        mock_client = AsyncMock()
        adapter = OKXTradingAdapter(mock_client)
        return adapter, mock_client

    @pytest.mark.asyncio
    async def test_place_order(self) -> None:
        adapter, mock = self._make_adapter()
        mock.place_order.return_value = {
            "code": "0",
            "msg": "",
            "data": [{"ordId": "98765", "clOrdId": "my-order"}],
        }

        req = OrderRequest(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=0.01,
            price=60000.0,
        )
        result = await adapter.place_order(req)

        assert result.exchange == "okx"
        assert result.order_id == "98765"
        assert result.status == OrderStatus.ACCEPTED

    @pytest.mark.asyncio
    async def test_get_balances(self) -> None:
        adapter, mock = self._make_adapter()
        mock.get_balance.return_value = {
            "code": "0",
            "data": [
                {
                    "details": [
                        {"ccy": "USDT", "availBal": "5000", "frozenBal": "200", "cashBal": "5200"},
                        {"ccy": "BTC", "availBal": "0.1", "frozenBal": "0", "cashBal": "0.1"},
                    ]
                }
            ],
        }
        balances = await adapter.get_balances()
        assert len(balances) == 2
        assert balances[0].asset == "USDT"
        assert balances[0].free == 5000.0

    @pytest.mark.asyncio
    async def test_exchange_name(self) -> None:
        adapter, _ = self._make_adapter()
        assert adapter.exchange_name == "okx"

    def test_parse_single_order(self) -> None:
        adapter, _ = self._make_adapter()
        result = adapter._parse_single_order({
            "ordId": "111",
            "clOrdId": "c1",
            "instId": "ETH-USDT",
            "side": "sell",
            "ordType": "limit",
            "state": "filled",
            "sz": "2.0",
            "fillSz": "2.0",
            "px": "3500",
            "avgPx": "3498",
        })
        assert result.status == OrderStatus.FILLED
        assert result.symbol == "ETH/USDT"
        assert result.avg_fill_price == 3498.0


# ---------------------------------------------------------------------------
# PolymarketTradingAdapter
# ---------------------------------------------------------------------------


class TestPolymarketTradingAdapter:
    def _make_adapter(self) -> tuple[PolymarketTradingAdapter, AsyncMock]:
        mock_client = AsyncMock()
        adapter = PolymarketTradingAdapter(mock_client)
        return adapter, mock_client

    @pytest.mark.asyncio
    async def test_place_order(self) -> None:
        adapter, mock = self._make_adapter()
        mock.place_order.return_value = {
            "orderID": "poly-order-1",
            "status": "live",
        }

        req = OrderRequest(
            symbol="token-abc",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=10.0,
            price=0.52,
        )
        result = await adapter.place_order(req)

        assert result.exchange == "polymarket"
        assert result.order_id == "poly-order-1"
        mock.place_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_balances(self) -> None:
        adapter, mock = self._make_adapter()
        mock.get_balance.return_value = {"balance": "1000.50"}
        balances = await adapter.get_balances()
        assert len(balances) == 1
        assert balances[0].asset == "USDC"
        assert balances[0].free == 1000.50

    @pytest.mark.asyncio
    async def test_exchange_name(self) -> None:
        adapter, _ = self._make_adapter()
        assert adapter.exchange_name == "polymarket"


# ---------------------------------------------------------------------------
# BalanceInfo
# ---------------------------------------------------------------------------


class TestBalanceInfo:
    def test_creation(self) -> None:
        b = BalanceInfo(asset="BTC", free=1.0, locked=0.5, total=1.5)
        assert b.total == 1.5

    def test_defaults(self) -> None:
        b = BalanceInfo(asset="USDT")
        assert b.free == 0.0
        assert b.locked == 0.0
        assert b.total == 0.0
