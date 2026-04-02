"""Binance Spot REST trading client.

Endpoints implemented (all require HMAC-SHA256 signed requests):
- POST   /api/v3/order          — place new order
- DELETE /api/v3/order          — cancel order
- GET    /api/v3/order          — query order status
- GET    /api/v3/openOrders     — list open orders
- GET    /api/v3/allOrders      — list all orders
- GET    /api/v3/account        — account info + balances

Docs: https://binance-docs.github.io/apidocs/spot/en/
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any

import httpx

from pnlclaw_exchange.base.auth import BinanceAuthenticator, ExchangeCredentials
from pnlclaw_exchange.base.rate_limiter import SlidingWindowRateLimiter
from pnlclaw_exchange.base.rest_client import BaseRESTClient
from pnlclaw_exchange.exceptions import (
    AuthenticationError,
    ExchangeAPIError,
    InsufficientBalanceError,
    InvalidOrderError,
    OrderNotFoundError,
    OrderRejectedError,
    RateLimitExceededError,
)

logger = logging.getLogger(__name__)

BINANCE_API_URL = "https://api.binance.com"
BINANCE_TESTNET_URL = "https://testnet.binance.vision"


class BinanceOrderType(str, Enum):
    """Binance order types."""

    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"
    LIMIT_MAKER = "LIMIT_MAKER"


class BinanceTimeInForce(str, Enum):
    """Time in force options."""

    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"


class BinanceRESTClient(BaseRESTClient):
    """Authenticated Binance Spot REST client for trading operations.

    Usage::

        creds = ExchangeCredentials(api_key="...", api_secret="...")
        client = BinanceRESTClient(credentials=creds)

        # Place a limit buy order
        result = await client.place_order(
            symbol="BTCUSDT",
            side="BUY",
            order_type=BinanceOrderType.LIMIT,
            quantity="0.001",
            price="60000",
            time_in_force=BinanceTimeInForce.GTC,
        )

        await client.close()
    """

    def __init__(
        self,
        credentials: ExchangeCredentials,
        *,
        testnet: bool = False,
        base_url: str | None = None,
        rate_limiter: SlidingWindowRateLimiter | None = None,
        timeout: float = 15.0,
        recv_window: int = 5000,
    ) -> None:
        url = base_url or (BINANCE_TESTNET_URL if testnet else BINANCE_API_URL)
        auth = BinanceAuthenticator(credentials)
        limiter = rate_limiter or SlidingWindowRateLimiter(calls_per_window=1200, window_ms=60_000)
        super().__init__(
            base_url=url,
            authenticator=auth,
            rate_limiter=limiter,
            timeout=timeout,
            recv_window=recv_window,
        )
        self._testnet = testnet

    @property
    def _exchange_name(self) -> str:
        return "binance"

    # ------------------------------------------------------------------
    # Binance-specific request: params are sent as query string / form
    # ------------------------------------------------------------------

    async def _signed_request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a signed request using Binance's query-param signature scheme.

        Binance signs params (not JSON body), and sends API key via header.
        """
        await self._rate_limiter.acquire()

        if params is None:
            params = {}
        params["timestamp"] = str(int(time.time() * 1000))
        if self._recv_window is not None:
            params["recvWindow"] = str(self._recv_window)

        auth_headers = self._auth.sign_request(method=method, path=path, params=params)

        url = f"{self._base_url}{path}"
        logger.debug("Binance REST %s %s", method, path)

        if method.upper() in ("POST", "PUT"):
            resp = await self._http.request(method=method, url=url, data=params, headers=auth_headers)
        else:
            resp = await self._http.request(method=method, url=url, params=params, headers=auth_headers)

        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            self._rate_limiter.set_retry_after(retry_after)

        if resp.status_code >= 400:
            self._handle_error_response(resp)

        result: dict[str, Any] = resp.json()
        return result

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def _handle_error_response(self, resp: httpx.Response) -> None:
        """Map Binance error codes to typed exceptions."""
        try:
            data = resp.json()
        except Exception:
            data = {"msg": resp.text}

        code = data.get("code", 0)
        msg = data.get("msg", str(data))

        if resp.status_code == 429:
            raise RateLimitExceededError(f"Binance rate limit: {msg}", exchange="binance", status_code=429)

        if resp.status_code in (401, 403) or code in (-2015, -2014, -1022):
            raise AuthenticationError(
                f"Binance auth error: {msg}",
                exchange="binance",
                status_code=resp.status_code,
            )

        if code == -2010:
            raise InsufficientBalanceError(f"Insufficient balance: {msg}", exchange="binance")

        if code in (-2011, -2013):
            raise OrderNotFoundError(f"Order not found: {msg}", exchange="binance")

        if code in (-1013, -1111, -1116, -1117, -1121):
            raise OrderRejectedError(f"Order rejected: {msg}", exchange="binance", details=data)

        raise ExchangeAPIError(
            f"Binance API error ({code}): {msg}",
            exchange="binance",
            status_code=resp.status_code,
            details=data,
        )

    # ------------------------------------------------------------------
    # Trading endpoints
    # ------------------------------------------------------------------

    async def place_order(
        self,
        *,
        symbol: str,
        side: str,
        order_type: str | BinanceOrderType,
        quantity: str | None = None,
        quote_order_qty: str | None = None,
        price: str | None = None,
        time_in_force: str | BinanceTimeInForce | None = None,
        stop_price: str | None = None,
        new_client_order_id: str | None = None,
        new_order_resp_type: str = "FULL",
    ) -> dict[str, Any]:
        """Place a new order on Binance Spot.

        Args:
            symbol: Trading pair (e.g. ``BTCUSDT``).
            side: ``BUY`` or ``SELL``.
            order_type: One of LIMIT, MARKET, STOP_LOSS, etc.
            quantity: Base asset quantity.
            quote_order_qty: Quote asset amount (for MARKET orders).
            price: Limit price.
            time_in_force: GTC, IOC, or FOK (required for LIMIT).
            stop_price: Stop trigger price (for stop orders).
            new_client_order_id: Custom order ID.
            new_order_resp_type: Response detail level (ACK, RESULT, FULL).

        Returns:
            Order response with orderId, status, fills, etc.
        """
        params: dict[str, Any] = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": str(order_type).upper(),
            "newOrderRespType": new_order_resp_type,
        }

        if quantity is not None:
            params["quantity"] = quantity
        if quote_order_qty is not None:
            params["quoteOrderQty"] = quote_order_qty
        if price is not None:
            params["price"] = price
        if time_in_force is not None:
            params["timeInForce"] = str(time_in_force).upper()
        if stop_price is not None:
            params["stopPrice"] = stop_price
        if new_client_order_id is not None:
            params["newClientOrderId"] = new_client_order_id

        self._validate_order_params(params)
        return await self._signed_request("POST", "/api/v3/order", params=params)

    async def cancel_order(
        self,
        *,
        symbol: str,
        order_id: int | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Cancel an active order.

        Args:
            symbol: Trading pair.
            order_id: Exchange-assigned order ID.
            client_order_id: Client-assigned order ID.

        Returns:
            Cancelled order details.
        """
        params: dict[str, Any] = {"symbol": symbol.upper()}
        if order_id is not None:
            params["orderId"] = str(order_id)
        if client_order_id is not None:
            params["origClientOrderId"] = client_order_id

        if "orderId" not in params and "origClientOrderId" not in params:
            raise InvalidOrderError("Either order_id or client_order_id is required", exchange="binance")

        return await self._signed_request("DELETE", "/api/v3/order", params=params)

    async def get_order(
        self,
        *,
        symbol: str,
        order_id: int | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Query a specific order's status.

        Args:
            symbol: Trading pair.
            order_id: Exchange order ID.
            client_order_id: Client order ID.

        Returns:
            Order details including status, filled qty, etc.
        """
        params: dict[str, Any] = {"symbol": symbol.upper()}
        if order_id is not None:
            params["orderId"] = str(order_id)
        if client_order_id is not None:
            params["origClientOrderId"] = client_order_id
        return await self._signed_request("GET", "/api/v3/order", params=params)

    async def get_open_orders(self, *, symbol: str | None = None) -> list[dict[str, Any]]:
        """Get all open orders, optionally filtered by symbol.

        Args:
            symbol: Trading pair. If None, returns all open orders.
        """
        params: dict[str, Any] = {}
        if symbol is not None:
            params["symbol"] = symbol.upper()
        result = await self._signed_request("GET", "/api/v3/openOrders", params=params)
        return result if isinstance(result, list) else [result]

    async def get_all_orders(
        self,
        *,
        symbol: str,
        limit: int = 500,
        order_id: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get all orders (open, filled, cancelled) for a symbol.

        Args:
            symbol: Trading pair.
            limit: Max results (default 500, max 1000).
            order_id: Start from this order ID.
            start_time: Start time filter (ms epoch).
            end_time: End time filter (ms epoch).
        """
        params: dict[str, Any] = {
            "symbol": symbol.upper(),
            "limit": str(min(limit, 1000)),
        }
        if order_id is not None:
            params["orderId"] = str(order_id)
        if start_time is not None:
            params["startTime"] = str(start_time)
        if end_time is not None:
            params["endTime"] = str(end_time)

        result = await self._signed_request("GET", "/api/v3/allOrders", params=params)
        return result if isinstance(result, list) else [result]

    # ------------------------------------------------------------------
    # Account endpoints
    # ------------------------------------------------------------------

    async def get_account(self, *, omit_zero_balances: bool = True) -> dict[str, Any]:
        """Get account information including balances and permissions.

        Args:
            omit_zero_balances: Exclude assets with zero balance.
        """
        params: dict[str, Any] = {}
        if omit_zero_balances:
            params["omitZeroBalances"] = "true"
        return await self._signed_request("GET", "/api/v3/account", params=params)

    async def get_balances(self) -> list[dict[str, str]]:
        """Get non-zero account balances.

        Returns:
            List of ``{"asset": "BTC", "free": "0.1", "locked": "0.0"}``.
        """
        account = await self.get_account(omit_zero_balances=True)
        balances: list[dict[str, str]] = account.get("balances", [])
        return balances

    # ------------------------------------------------------------------
    # Public endpoints (no auth)
    # ------------------------------------------------------------------

    async def get_exchange_info(self, symbol: str | None = None) -> dict[str, Any]:
        """Get exchange trading rules and symbol info (public, no auth)."""
        params: dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol.upper()
        url = f"{self._base_url}/api/v3/exchangeInfo"
        resp = await self._http.get(url, params=params or None)
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result

    async def test_connectivity(self) -> bool:
        """Ping the API server (public endpoint). Returns True if reachable."""
        try:
            resp = await self._http.get(f"{self._base_url}/api/v3/ping")
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_order_params(params: dict[str, Any]) -> None:
        """Client-side parameter validation before sending to Binance."""
        order_type = params.get("type", "")

        if order_type == "LIMIT":
            for field in ("quantity", "price", "timeInForce"):
                if field not in params:
                    raise InvalidOrderError(f"LIMIT order requires '{field}'", exchange="binance")

        elif order_type == "MARKET":
            if "quantity" not in params and "quoteOrderQty" not in params:
                raise InvalidOrderError(
                    "MARKET order requires 'quantity' or 'quoteOrderQty'",
                    exchange="binance",
                )

        elif order_type in ("STOP_LOSS", "TAKE_PROFIT"):
            if "quantity" not in params:
                raise InvalidOrderError(f"{order_type} order requires 'quantity'", exchange="binance")
            if "stopPrice" not in params:
                raise InvalidOrderError(f"{order_type} order requires 'stopPrice'", exchange="binance")

        elif order_type in ("STOP_LOSS_LIMIT", "TAKE_PROFIT_LIMIT"):
            for field in ("quantity", "price", "timeInForce", "stopPrice"):
                if field not in params:
                    raise InvalidOrderError(f"{order_type} order requires '{field}'", exchange="binance")
