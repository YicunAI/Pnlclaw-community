"""Polymarket CLOB trading client for placing and managing prediction market orders.

Polymarket uses a Central Limit Order Book (CLOB) system on Polygon L2.
Authentication uses:
- API Key + Secret derived from wallet signature
- EIP-712 typed data signing for order creation

Endpoints (CLOB API — https://clob.polymarket.com):
- POST /order          — place a new order
- DELETE /order        — cancel order
- GET  /orders         — list active orders
- GET  /trades         — trade history
- GET  /balance        — USDC balance

Docs: https://docs.polymarket.com/
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from enum import Enum
from typing import Any

import httpx

from pnlclaw_exchange.base.rate_limiter import SlidingWindowRateLimiter
from pnlclaw_exchange.exceptions import (
    AuthenticationError,
    ExchangeAPIError,
    InsufficientBalanceError,
    InvalidOrderError,
    OrderNotFoundError,
    OrderRejectedError,
)

logger = logging.getLogger(__name__)

POLYMARKET_CLOB_URL = "https://clob.polymarket.com"


class PolymarketOrderType(str, Enum):
    """Polymarket order types."""

    GTC = "GTC"
    FOK = "FOK"
    GTD = "GTD"


class PolymarketSide(str, Enum):
    """Polymarket order side."""

    BUY = "BUY"
    SELL = "SELL"


class PolymarketCredentials:
    """Polymarket CLOB API credentials.

    The CLOB API uses an API key + secret pair, plus the wallet
    address and a signing function for EIP-712 order creation.

    Users derive their API key/secret by signing a message with their
    Polygon wallet. This client accepts pre-derived credentials.
    """

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        api_passphrase: str,
        wallet_address: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.wallet_address = wallet_address


class PolymarketTradingClient:
    """Authenticated Polymarket CLOB trading client.

    Provides order placement, cancellation, and query operations
    for the Polymarket prediction market CLOB.

    Usage::

        creds = PolymarketCredentials(
            api_key="...",
            api_secret="...",
            api_passphrase="...",
        )
        client = PolymarketTradingClient(credentials=creds)

        result = await client.place_order(
            token_id="1535318560...",
            side=PolymarketSide.BUY,
            price=0.52,
            size=10.0,
        )

        await client.close()
    """

    def __init__(
        self,
        credentials: PolymarketCredentials,
        *,
        base_url: str = POLYMARKET_CLOB_URL,
        rate_limiter: SlidingWindowRateLimiter | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._creds = credentials
        self._base_url = base_url.rstrip("/")
        self._rate_limiter = rate_limiter or SlidingWindowRateLimiter(
            calls_per_window=100, window_ms=10_000
        )
        self._http = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Auth headers
    # ------------------------------------------------------------------

    def _build_auth_headers(
        self,
        method: str,
        path: str,
        body: str = "",
    ) -> dict[str, str]:
        """Build HMAC-signed headers for Polymarket CLOB API.

        The signature covers: timestamp + method + path + body
        """
        timestamp = str(int(time.time()))
        prehash = timestamp + method.upper() + path + body

        signature = hmac.new(
            self._creds.api_secret.encode("utf-8"),
            prehash.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return {
            "POLY-ADDRESS": self._creds.wallet_address or "",
            "POLY-SIGNATURE": signature,
            "POLY-TIMESTAMP": timestamp,
            "POLY-API-KEY": self._creds.api_key,
            "POLY-PASSPHRASE": self._creds.api_passphrase,
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Internal request
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send an authenticated CLOB API request."""
        await self._rate_limiter.acquire()

        body_str = json.dumps(body) if body else ""
        headers = self._build_auth_headers(method, path, body_str)

        url = f"{self._base_url}{path}"
        logger.debug("Polymarket REST %s %s", method, path)

        resp = await self._http.request(
            method=method,
            url=url,
            params=params,
            content=body_str if body_str else None,
            headers=headers,
        )

        if resp.status_code in (401, 403):
            raise AuthenticationError(
                "Polymarket authentication failed",
                exchange="polymarket",
                status_code=resp.status_code,
            )

        if resp.status_code >= 400:
            self._handle_error(resp)

        try:
            result: dict[str, Any] = resp.json()
            return result
        except Exception:
            return {"raw": resp.text}

    def _handle_error(self, resp: httpx.Response) -> None:
        """Map Polymarket error responses to typed exceptions."""
        try:
            data = resp.json()
        except Exception:
            data = {"error": resp.text}

        error_msg = data.get("error", data.get("message", str(data)))

        if "insufficient" in str(error_msg).lower() or "balance" in str(error_msg).lower():
            raise InsufficientBalanceError(
                f"Polymarket: {error_msg}", exchange="polymarket"
            )

        if "not found" in str(error_msg).lower():
            raise OrderNotFoundError(
                f"Polymarket: {error_msg}", exchange="polymarket"
            )

        if resp.status_code == 400:
            raise OrderRejectedError(
                f"Polymarket order rejected: {error_msg}",
                exchange="polymarket",
                details=data,
            )

        raise ExchangeAPIError(
            f"Polymarket API error ({resp.status_code}): {error_msg}",
            exchange="polymarket",
            status_code=resp.status_code,
            details=data,
        )

    # ------------------------------------------------------------------
    # Trading endpoints
    # ------------------------------------------------------------------

    async def place_order(
        self,
        *,
        token_id: str,
        side: str | PolymarketSide,
        price: float,
        size: float,
        order_type: str | PolymarketOrderType = PolymarketOrderType.GTC,
        expiration: int | None = None,
    ) -> dict[str, Any]:
        """Place a new order on the Polymarket CLOB.

        Args:
            token_id: The outcome token ID to trade.
            side: ``BUY`` or ``SELL``.
            price: Price in dollars (0.01 to 0.99 for binary markets).
            size: Number of shares.
            order_type: GTC, FOK, or GTD.
            expiration: Unix timestamp for GTD orders.

        Returns:
            Order response with order_id, status, etc.
        """
        if price <= 0 or price >= 1:
            raise InvalidOrderError(
                "Polymarket price must be between 0.01 and 0.99",
                exchange="polymarket",
            )
        if size <= 0:
            raise InvalidOrderError(
                "Order size must be positive", exchange="polymarket"
            )

        body: dict[str, Any] = {
            "tokenID": token_id,
            "side": str(side).upper(),
            "price": str(price),
            "size": str(size),
            "type": str(order_type).upper(),
        }

        if expiration is not None:
            body["expiration"] = str(expiration)

        return await self._request("POST", "/order", body=body)

    async def cancel_order(self, *, order_id: str) -> dict[str, Any]:
        """Cancel a pending order.

        Args:
            order_id: The order ID to cancel.
        """
        return await self._request("DELETE", "/order", body={"orderID": order_id})

    async def cancel_orders(self, *, order_ids: list[str]) -> dict[str, Any]:
        """Cancel multiple orders at once.

        Args:
            order_ids: List of order IDs to cancel.
        """
        return await self._request(
            "DELETE", "/orders", body={"orderIDs": order_ids}
        )

    async def cancel_all_orders(self) -> dict[str, Any]:
        """Cancel all active orders."""
        return await self._request("DELETE", "/cancel-all")

    async def get_active_orders(
        self,
        *,
        market: str | None = None,
        asset_id: str | None = None,
    ) -> dict[str, Any]:
        """Get all active (open) orders.

        Args:
            market: Filter by market/condition ID.
            asset_id: Filter by token ID.
        """
        params: dict[str, Any] = {}
        if market:
            params["market"] = market
        if asset_id:
            params["asset_id"] = asset_id
        return await self._request("GET", "/orders", params=params or None)

    async def get_trades(
        self,
        *,
        market: str | None = None,
        asset_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Get trade history.

        Args:
            market: Filter by market/condition ID.
            asset_id: Filter by token ID.
            limit: Max results.
        """
        params: dict[str, Any] = {"limit": str(limit)}
        if market:
            params["market"] = market
        if asset_id:
            params["asset_id"] = asset_id
        return await self._request("GET", "/trades", params=params)

    # ------------------------------------------------------------------
    # Balance endpoints
    # ------------------------------------------------------------------

    async def get_balance(self) -> dict[str, Any]:
        """Get USDC balance on the CLOB."""
        return await self._request("GET", "/balance")

    async def get_token_balance(self, token_id: str) -> dict[str, Any]:
        """Get balance for a specific outcome token.

        Args:
            token_id: The token ID to check.
        """
        return await self._request("GET", f"/balance/{token_id}")

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    async def test_connectivity(self) -> bool:
        """Check if Polymarket CLOB API is reachable."""
        try:
            resp = await self._http.get(f"{self._base_url}/time")
            return resp.status_code == 200
        except Exception:
            return False
