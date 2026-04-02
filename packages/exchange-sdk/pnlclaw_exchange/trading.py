"""Unified trading interface for all exchanges.

Provides a Protocol-based abstraction that normalizes order operations
across Binance, OKX, and Polymarket into a common interface. This enables
the agent-runtime and strategy-engine to place orders without knowing
the exchange-specific API details.
"""

from __future__ import annotations

import logging
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from pnlclaw_types.trading import OrderSide, OrderStatus, OrderType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Unified order request / response
# ---------------------------------------------------------------------------


class OrderRequest(BaseModel):
    """Exchange-agnostic order request.

    This is the unified interface that agents and strategies use.
    The exchange adapter translates it into exchange-specific parameters.
    """

    symbol: str = Field(..., description="Trading pair (e.g. 'BTC/USDT', or token_id for Polymarket)")
    side: OrderSide = Field(..., description="Buy or sell")
    order_type: OrderType = Field(..., description="Market, limit, stop_market, stop_limit")
    quantity: float = Field(..., gt=0, description="Amount to trade")
    price: float | None = Field(None, ge=0, description="Limit price (required for limit orders)")
    stop_price: float | None = Field(None, ge=0, description="Stop trigger price")
    time_in_force: str = Field("GTC", description="Time in force: GTC, IOC, FOK")
    client_order_id: str | None = Field(None, description="Custom order ID")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "symbol": "BTC/USDT",
                    "side": "buy",
                    "order_type": "limit",
                    "quantity": 0.001,
                    "price": 60000.0,
                    "time_in_force": "GTC",
                }
            ]
        }
    }


class OrderResponse(BaseModel):
    """Normalized response after placing/cancelling an order."""

    exchange: str = Field(..., description="Exchange name")
    order_id: str = Field(..., description="Exchange-assigned order ID")
    client_order_id: str = Field("", description="Client-assigned order ID")
    symbol: str = Field(..., description="Trading pair")
    side: OrderSide
    order_type: OrderType
    status: OrderStatus
    quantity: float
    filled_quantity: float = 0.0
    price: float | None = None
    avg_fill_price: float | None = None
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))
    raw: dict[str, Any] = Field(default_factory=dict, description="Raw exchange response")


class BalanceInfo(BaseModel):
    """Normalized account balance for a single asset."""

    asset: str
    free: float = 0.0
    locked: float = 0.0
    total: float = 0.0


# ---------------------------------------------------------------------------
# Trading client Protocol
# ---------------------------------------------------------------------------


class TradingClient(ABC):
    """Unified trading client interface.

    All exchange-specific clients implement this ABC, providing a consistent
    API for the agent-runtime and strategy execution pipeline.
    """

    @property
    @abstractmethod
    def exchange_name(self) -> str:
        """Return the exchange identifier."""

    @abstractmethod
    async def place_order(self, request: OrderRequest) -> OrderResponse:
        """Place a new order on the exchange.

        Args:
            request: Unified order request.

        Returns:
            Normalized order response.
        """

    @abstractmethod
    async def cancel_order(self, *, symbol: str, order_id: str) -> OrderResponse:
        """Cancel an existing order.

        Args:
            symbol: Trading pair.
            order_id: Exchange order ID.
        """

    @abstractmethod
    async def get_order(self, *, symbol: str, order_id: str) -> OrderResponse:
        """Get current status of an order.

        Args:
            symbol: Trading pair.
            order_id: Exchange order ID.
        """

    @abstractmethod
    async def get_open_orders(self, symbol: str | None = None) -> list[OrderResponse]:
        """Get all currently open orders."""

    @abstractmethod
    async def get_balances(self) -> list[BalanceInfo]:
        """Get account balances."""

    @abstractmethod
    async def test_connectivity(self) -> bool:
        """Check if the exchange is reachable."""

    async def close(self) -> None:
        """Close underlying connections. Override if needed."""


# ---------------------------------------------------------------------------
# Binance adapter
# ---------------------------------------------------------------------------


class BinanceTradingAdapter(TradingClient):
    """Adapts BinanceRESTClient to the unified TradingClient interface."""

    def __init__(self, client: Any) -> None:
        """Args:
        client: A ``BinanceRESTClient`` instance.
        """
        self._client = client

    @property
    def exchange_name(self) -> str:
        return "binance"

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        binance_symbol = request.symbol.replace("/", "")

        type_map = {
            OrderType.MARKET: "MARKET",
            OrderType.LIMIT: "LIMIT",
            OrderType.STOP_MARKET: "STOP_LOSS",
            OrderType.STOP_LIMIT: "STOP_LOSS_LIMIT",
        }
        binance_type = type_map.get(request.order_type, "MARKET")

        kwargs: dict[str, Any] = {
            "symbol": binance_symbol,
            "side": request.side.value.upper(),
            "order_type": binance_type,
            "quantity": str(request.quantity),
        }
        if request.price is not None:
            kwargs["price"] = str(request.price)
        if request.stop_price is not None:
            kwargs["stop_price"] = str(request.stop_price)
        if request.time_in_force and request.order_type != OrderType.MARKET:
            kwargs["time_in_force"] = request.time_in_force
        if request.client_order_id:
            kwargs["new_client_order_id"] = request.client_order_id

        raw = await self._client.place_order(**kwargs)
        return self._parse_order_response(raw)

    async def cancel_order(self, *, symbol: str, order_id: str) -> OrderResponse:
        raw = await self._client.cancel_order(symbol=symbol.replace("/", ""), order_id=int(order_id))
        return self._parse_order_response(raw)

    async def get_order(self, *, symbol: str, order_id: str) -> OrderResponse:
        raw = await self._client.get_order(symbol=symbol.replace("/", ""), order_id=int(order_id))
        return self._parse_order_response(raw)

    async def get_open_orders(self, symbol: str | None = None) -> list[OrderResponse]:
        binance_symbol = symbol.replace("/", "") if symbol else None
        raw_list = await self._client.get_open_orders(symbol=binance_symbol)
        return [self._parse_order_response(r) for r in raw_list]

    async def get_balances(self) -> list[BalanceInfo]:
        raw_list = await self._client.get_balances()
        return [
            BalanceInfo(
                asset=b["asset"],
                free=float(b.get("free", 0)),
                locked=float(b.get("locked", 0)),
                total=float(b.get("free", 0)) + float(b.get("locked", 0)),
            )
            for b in raw_list
        ]

    async def test_connectivity(self) -> bool:
        result: bool = await self._client.test_connectivity()
        return result

    async def close(self) -> None:
        await self._client.close()

    def _parse_order_response(self, raw: dict[str, Any]) -> OrderResponse:
        status_map = {
            "NEW": OrderStatus.ACCEPTED,
            "PARTIALLY_FILLED": OrderStatus.PARTIAL,
            "FILLED": OrderStatus.FILLED,
            "CANCELED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
            "EXPIRED": OrderStatus.CANCELLED,
        }

        type_map = {
            "LIMIT": OrderType.LIMIT,
            "MARKET": OrderType.MARKET,
            "STOP_LOSS": OrderType.STOP_MARKET,
            "STOP_LOSS_LIMIT": OrderType.STOP_LIMIT,
            "TAKE_PROFIT": OrderType.STOP_MARKET,
            "TAKE_PROFIT_LIMIT": OrderType.STOP_LIMIT,
            "LIMIT_MAKER": OrderType.LIMIT,
        }

        side_map = {"BUY": OrderSide.BUY, "SELL": OrderSide.SELL}

        executed_qty = float(raw.get("executedQty", 0))
        cum_quote = float(raw.get("cummulativeQuoteQty", 0))
        avg_price = (cum_quote / executed_qty) if executed_qty > 0 else None

        return OrderResponse(
            exchange="binance",
            order_id=str(raw.get("orderId", "")),
            client_order_id=raw.get("clientOrderId", ""),
            symbol=raw.get("symbol", ""),
            side=side_map.get(raw.get("side", "BUY"), OrderSide.BUY),
            order_type=type_map.get(raw.get("type", "MARKET"), OrderType.MARKET),
            status=status_map.get(raw.get("status", "NEW"), OrderStatus.ACCEPTED),
            quantity=float(raw.get("origQty", 0)),
            filled_quantity=executed_qty,
            price=float(raw["price"]) if raw.get("price") and float(raw["price"]) > 0 else None,
            avg_fill_price=avg_price,
            timestamp=int(raw.get("transactTime", raw.get("time", time.time() * 1000))),
            raw=raw,
        )


# ---------------------------------------------------------------------------
# OKX adapter
# ---------------------------------------------------------------------------


class OKXTradingAdapter(TradingClient):
    """Adapts OKXRESTClient to the unified TradingClient interface."""

    def __init__(self, client: Any) -> None:
        self._client = client

    @property
    def exchange_name(self) -> str:
        return "okx"

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        okx_symbol = request.symbol.replace("/", "-")

        type_map = {
            OrderType.MARKET: "market",
            OrderType.LIMIT: "limit",
            OrderType.STOP_MARKET: "market",
            OrderType.STOP_LIMIT: "limit",
        }

        kwargs: dict[str, Any] = {
            "inst_id": okx_symbol,
            "side": request.side.value,
            "order_type": type_map.get(request.order_type, "market"),
            "size": str(request.quantity),
        }
        if request.price is not None:
            kwargs["price"] = str(request.price)
        if request.client_order_id:
            kwargs["client_order_id"] = request.client_order_id

        raw = await self._client.place_order(**kwargs)
        return self._parse_order_response(raw, request)

    async def cancel_order(self, *, symbol: str, order_id: str) -> OrderResponse:
        okx_symbol = symbol.replace("/", "-")
        raw = await self._client.cancel_order(inst_id=okx_symbol, order_id=order_id)
        return self._parse_cancel_response(raw, symbol)

    async def get_order(self, *, symbol: str, order_id: str) -> OrderResponse:
        okx_symbol = symbol.replace("/", "-")
        raw = await self._client.get_order(inst_id=okx_symbol, order_id=order_id)
        return self._parse_query_response(raw)

    async def get_open_orders(self, symbol: str | None = None) -> list[OrderResponse]:
        inst_id = symbol.replace("/", "-") if symbol else None
        raw = await self._client.get_open_orders(inst_id=inst_id)
        results: list[OrderResponse] = []
        for item in raw.get("data", []):
            results.append(self._parse_single_order(item))
        return results

    async def get_balances(self) -> list[BalanceInfo]:
        raw = await self._client.get_balance()
        balances: list[BalanceInfo] = []
        for detail in raw.get("data", [{}])[0].get("details", []):
            balances.append(
                BalanceInfo(
                    asset=detail.get("ccy", ""),
                    free=float(detail.get("availBal", 0)),
                    locked=float(detail.get("frozenBal", 0)),
                    total=float(detail.get("cashBal", 0)),
                )
            )
        return balances

    async def test_connectivity(self) -> bool:
        result: bool = await self._client.test_connectivity()
        return result

    async def close(self) -> None:
        await self._client.close()

    def _parse_order_response(self, raw: dict[str, Any], request: OrderRequest) -> OrderResponse:
        data = raw.get("data", [{}])
        item = data[0] if data else {}

        return OrderResponse(
            exchange="okx",
            order_id=item.get("ordId", ""),
            client_order_id=item.get("clOrdId", ""),
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            status=OrderStatus.ACCEPTED,
            quantity=request.quantity,
            price=request.price,
            raw=raw,
        )

    def _parse_cancel_response(self, raw: dict[str, Any], symbol: str) -> OrderResponse:
        data = raw.get("data", [{}])
        item = data[0] if data else {}

        return OrderResponse(
            exchange="okx",
            order_id=item.get("ordId", ""),
            client_order_id=item.get("clOrdId", ""),
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            status=OrderStatus.CANCELLED,
            quantity=0,
            raw=raw,
        )

    def _parse_query_response(self, raw: dict[str, Any]) -> OrderResponse:
        data = raw.get("data", [{}])
        if data:
            return self._parse_single_order(data[0])
        return OrderResponse(
            exchange="okx",
            order_id="",
            symbol="",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            status=OrderStatus.REJECTED,
            quantity=0,
            raw=raw,
        )

    def _parse_single_order(self, item: dict[str, Any]) -> OrderResponse:
        status_map = {
            "live": OrderStatus.ACCEPTED,
            "partially_filled": OrderStatus.PARTIAL,
            "filled": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
            "cancelled": OrderStatus.CANCELLED,
        }

        type_map = {
            "market": OrderType.MARKET,
            "limit": OrderType.LIMIT,
            "post_only": OrderType.LIMIT,
            "fok": OrderType.LIMIT,
            "ioc": OrderType.LIMIT,
        }

        side_map = {"buy": OrderSide.BUY, "sell": OrderSide.SELL}

        fill_sz = float(item.get("fillSz", 0) or 0)
        avg_px_str = item.get("avgPx", "")
        avg_px = float(avg_px_str) if avg_px_str else None

        return OrderResponse(
            exchange="okx",
            order_id=item.get("ordId", ""),
            client_order_id=item.get("clOrdId", ""),
            symbol=item.get("instId", "").replace("-", "/"),
            side=side_map.get(item.get("side", "buy"), OrderSide.BUY),
            order_type=type_map.get(item.get("ordType", "market"), OrderType.MARKET),
            status=status_map.get(item.get("state", "live"), OrderStatus.ACCEPTED),
            quantity=float(item.get("sz", 0) or 0),
            filled_quantity=fill_sz,
            price=float(item["px"]) if item.get("px") else None,
            avg_fill_price=avg_px,
            raw=item,
        )


# ---------------------------------------------------------------------------
# Polymarket adapter
# ---------------------------------------------------------------------------


class PolymarketTradingAdapter(TradingClient):
    """Adapts PolymarketTradingClient to the unified TradingClient interface."""

    def __init__(self, client: Any) -> None:
        self._client = client

    @property
    def exchange_name(self) -> str:
        return "polymarket"

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        raw = await self._client.place_order(
            token_id=request.symbol,
            side=request.side.value.upper(),
            price=request.price or 0.5,
            size=request.quantity,
        )
        return OrderResponse(
            exchange="polymarket",
            order_id=raw.get("orderID", raw.get("id", str(uuid.uuid4()))),
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            status=OrderStatus.ACCEPTED,
            quantity=request.quantity,
            price=request.price,
            raw=raw,
        )

    async def cancel_order(self, *, symbol: str, order_id: str) -> OrderResponse:
        raw = await self._client.cancel_order(order_id=order_id)
        return OrderResponse(
            exchange="polymarket",
            order_id=order_id,
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            status=OrderStatus.CANCELLED,
            quantity=0,
            raw=raw,
        )

    async def get_order(self, *, symbol: str, order_id: str) -> OrderResponse:
        raw = await self._client.get_active_orders(asset_id=symbol)
        orders = raw.get("data", raw.get("orders", []))
        for o in orders if isinstance(orders, list) else []:
            if o.get("id") == order_id or o.get("orderID") == order_id:
                return self._parse_poly_order(o)
        return OrderResponse(
            exchange="polymarket",
            order_id=order_id,
            symbol=symbol,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            status=OrderStatus.FILLED,
            quantity=0,
            raw=raw,
        )

    async def get_open_orders(self, symbol: str | None = None) -> list[OrderResponse]:
        raw = await self._client.get_active_orders(asset_id=symbol if symbol else None)
        orders = raw.get("data", raw.get("orders", []))
        return [self._parse_poly_order(o) for o in (orders if isinstance(orders, list) else [])]

    async def get_balances(self) -> list[BalanceInfo]:
        raw = await self._client.get_balance()
        balance = float(raw.get("balance", raw.get("amount", 0)))
        return [BalanceInfo(asset="USDC", free=balance, total=balance)]

    async def test_connectivity(self) -> bool:
        result: bool = await self._client.test_connectivity()
        return result

    async def close(self) -> None:
        await self._client.close()

    @staticmethod
    def _parse_poly_order(item: dict[str, Any]) -> OrderResponse:
        side_map = {"BUY": OrderSide.BUY, "SELL": OrderSide.SELL}
        return OrderResponse(
            exchange="polymarket",
            order_id=item.get("id", item.get("orderID", "")),
            symbol=item.get("asset_id", item.get("tokenID", "")),
            side=side_map.get(item.get("side", "BUY"), OrderSide.BUY),
            order_type=OrderType.LIMIT,
            status=OrderStatus.ACCEPTED,
            quantity=float(item.get("original_size", item.get("size", 0))),
            price=float(item.get("price", 0)),
            raw=item,
        )
