"""OKX REST trading client (API v5).

Endpoints implemented (all require HMAC-SHA256 + Base64 signed headers):
- POST /api/v5/trade/order       — place new order
- POST /api/v5/trade/cancel-order — cancel order
- GET  /api/v5/trade/order       — query order
- GET  /api/v5/trade/orders-pending — open orders
- GET  /api/v5/trade/orders-history-archive — order history
- GET  /api/v5/account/balance   — account balance
- GET  /api/v5/account/positions — positions

Docs: https://www.okx.com/docs-v5/en/
"""

from __future__ import annotations

import json
import logging
import time
from enum import Enum
from typing import Any

import httpx

from pnlclaw_exchange.base.auth import ExchangeCredentials, OKXAuthenticator
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

OKX_API_URL = "https://www.okx.com"
OKX_DEMO_URL = "https://www.okx.com"


class OKXOrderType(str, Enum):
    """OKX order types for spot trading."""

    MARKET = "market"
    LIMIT = "limit"
    POST_ONLY = "post_only"
    FOK = "fok"
    IOC = "ioc"


class OKXTradeMode(str, Enum):
    """OKX trade modes."""

    CASH = "cash"
    CROSS = "cross"
    ISOLATED = "isolated"


class OKXRESTClient(BaseRESTClient):
    """Authenticated OKX REST client for trading operations (API v5).

    OKX authentication uses four headers per request:
    - OK-ACCESS-KEY
    - OK-ACCESS-SIGN (HMAC-SHA256, Base64)
    - OK-ACCESS-TIMESTAMP (ISO 8601 UTC)
    - OK-ACCESS-PASSPHRASE

    Usage::

        from pydantic import SecretStr
        creds = ExchangeCredentials(
            api_key=SecretStr("..."),
            api_secret=SecretStr("..."),
            passphrase=SecretStr("..."),
        )
        client = OKXRESTClient(credentials=creds)

        result = await client.place_order(
            inst_id="BTC-USDT",
            side="buy",
            order_type=OKXOrderType.LIMIT,
            size="0.001",
            price="60000",
        )

        await client.close()
    """

    def __init__(
        self,
        credentials: ExchangeCredentials,
        *,
        demo: bool = False,
        base_url: str | None = None,
        rate_limiter: SlidingWindowRateLimiter | None = None,
        timeout: float = 15.0,
    ) -> None:
        url = base_url or OKX_API_URL
        auth = OKXAuthenticator(credentials)
        limiter = rate_limiter or SlidingWindowRateLimiter(
            calls_per_window=60, window_ms=2_000
        )
        super().__init__(
            base_url=url,
            authenticator=auth,
            rate_limiter=limiter,
            timeout=timeout,
        )
        self._demo = demo

    @property
    def _exchange_name(self) -> str:
        return "okx"

    # ------------------------------------------------------------------
    # OKX-specific request: JSON body + signed headers
    # ------------------------------------------------------------------

    async def _okx_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a signed OKX API v5 request.

        OKX signs ``timestamp + method + path[?query] + body`` and sends
        the signature in headers, not query params.
        """
        await self._rate_limiter.acquire()

        body_str = json.dumps(body) if body else ""

        auth_headers = self._auth.sign_request(
            method=method,
            path=path,
            params=params,
            body=body_str if body_str else None,
        )

        if self._demo:
            auth_headers["x-simulated-trading"] = "1"

        url = f"{self._base_url}{path}"
        query_params = params if method.upper() == "GET" and params else None

        logger.debug("OKX REST %s %s", method, path)

        resp = await self._http.request(
            method=method,
            url=url,
            params=query_params,
            content=body_str if method.upper() == "POST" else None,
            headers=auth_headers,
        )

        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            self._rate_limiter.set_retry_after(retry_after)

        data: dict[str, Any] = resp.json()

        if resp.status_code == 429:
            raise RateLimitExceededError(
                "OKX rate limit exceeded", exchange="okx", status_code=429
            )

        if resp.status_code in (401, 403):
            raise AuthenticationError(
                f"OKX auth error: {data.get('msg', '')}",
                exchange="okx",
                status_code=resp.status_code,
            )

        okx_code = data.get("code", "0")
        if okx_code != "0":
            self._handle_okx_error(data)

        return data

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def _handle_error_response(self, resp: httpx.Response) -> None:
        """Fallback for BaseRESTClient calls."""
        try:
            data = resp.json()
        except Exception:
            data = {"msg": resp.text}
        self._handle_okx_error(data, status_code=resp.status_code)

    def _handle_okx_error(
        self, data: dict[str, Any], status_code: int | None = None
    ) -> None:
        """Map OKX error codes to typed exceptions."""
        code = data.get("code", "0")
        msg = data.get("msg", "")

        sdata = data.get("data", [{}])
        if isinstance(sdata, list) and sdata:
            detail_msg = sdata[0].get("sMsg", "") or sdata[0].get("msg", "")
            detail_code = sdata[0].get("sCode", "") or sdata[0].get("code", "")
        else:
            detail_msg = msg
            detail_code = code

        full_msg = detail_msg or msg or f"OKX error {code}"

        if code in ("50101", "50102", "50103", "50104", "50105"):
            raise AuthenticationError(full_msg, exchange="okx")

        if detail_code in ("51008", "51127"):
            raise InsufficientBalanceError(full_msg, exchange="okx")

        if detail_code in ("51603", "51026"):
            raise OrderNotFoundError(full_msg, exchange="okx")

        if detail_code in ("51000", "51001", "51002", "51003", "51004",
                           "51006", "51020"):
            raise OrderRejectedError(full_msg, exchange="okx", details=data)

        raise ExchangeAPIError(
            f"OKX API error ({code}/{detail_code}): {full_msg}",
            exchange="okx",
            status_code=status_code,
            details=data,
        )

    # ------------------------------------------------------------------
    # Trading endpoints
    # ------------------------------------------------------------------

    async def place_order(
        self,
        *,
        inst_id: str,
        side: str,
        order_type: str | OKXOrderType,
        size: str,
        trade_mode: str | OKXTradeMode = OKXTradeMode.CASH,
        price: str | None = None,
        client_order_id: str | None = None,
        tag: str | None = None,
        reduce_only: bool = False,
        target_currency: str | None = None,
    ) -> dict[str, Any]:
        """Place a new order on OKX.

        Args:
            inst_id: Instrument ID (e.g. ``BTC-USDT``).
            side: ``buy`` or ``sell``.
            order_type: market, limit, post_only, fok, ioc.
            size: Quantity to trade.
            trade_mode: cash (spot), cross, or isolated.
            price: Order price (required for limit orders).
            client_order_id: Custom order ID (max 32 chars).
            tag: Order tag (max 16 chars).
            reduce_only: Only reduce position size.
            target_currency: base_ccy or quote_ccy for SPOT market orders.

        Returns:
            OKX response with ordId, clOrdId, etc.
        """
        body: dict[str, Any] = {
            "instId": inst_id,
            "tdMode": str(trade_mode),
            "side": side.lower(),
            "ordType": str(order_type).lower(),
            "sz": size,
        }

        if price is not None:
            body["px"] = price
        if client_order_id is not None:
            body["clOrdId"] = client_order_id
        if tag is not None:
            body["tag"] = tag
        if reduce_only:
            body["reduceOnly"] = True
        if target_currency is not None:
            body["tgtCcy"] = target_currency

        self._validate_order_params(body)
        return await self._okx_request("POST", "/api/v5/trade/order", body=body)

    async def cancel_order(
        self,
        *,
        inst_id: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Cancel a pending order.

        Args:
            inst_id: Instrument ID.
            order_id: OKX order ID.
            client_order_id: Client order ID.
        """
        body: dict[str, Any] = {"instId": inst_id}
        if order_id is not None:
            body["ordId"] = order_id
        if client_order_id is not None:
            body["clOrdId"] = client_order_id

        if "ordId" not in body and "clOrdId" not in body:
            raise InvalidOrderError(
                "Either order_id or client_order_id is required", exchange="okx"
            )

        return await self._okx_request("POST", "/api/v5/trade/cancel-order", body=body)

    async def get_order(
        self,
        *,
        inst_id: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """Query order details.

        Args:
            inst_id: Instrument ID.
            order_id: OKX order ID.
            client_order_id: Client order ID.
        """
        params: dict[str, Any] = {"instId": inst_id}
        if order_id is not None:
            params["ordId"] = order_id
        if client_order_id is not None:
            params["clOrdId"] = client_order_id
        return await self._okx_request("GET", "/api/v5/trade/order", params=params)

    async def get_open_orders(
        self,
        *,
        inst_id: str | None = None,
        order_type: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Get pending orders.

        Args:
            inst_id: Filter by instrument.
            order_type: Filter by order type.
            limit: Max results.
        """
        params: dict[str, Any] = {"limit": str(min(limit, 100))}
        if inst_id is not None:
            params["instId"] = inst_id
        if order_type is not None:
            params["ordType"] = order_type
        return await self._okx_request(
            "GET", "/api/v5/trade/orders-pending", params=params
        )

    async def get_order_history(
        self,
        *,
        inst_id: str | None = None,
        inst_type: str = "SPOT",
        limit: int = 100,
    ) -> dict[str, Any]:
        """Get order history (last 7 days).

        Args:
            inst_id: Filter by instrument.
            inst_type: SPOT, MARGIN, SWAP, FUTURES, OPTION.
            limit: Max results.
        """
        params: dict[str, Any] = {
            "instType": inst_type,
            "limit": str(min(limit, 100)),
        }
        if inst_id is not None:
            params["instId"] = inst_id
        return await self._okx_request(
            "GET", "/api/v5/trade/orders-history-archive", params=params
        )

    # ------------------------------------------------------------------
    # Account endpoints
    # ------------------------------------------------------------------

    async def get_balance(self, *, currencies: list[str] | None = None) -> dict[str, Any]:
        """Get account balance.

        Args:
            currencies: Filter by currency (e.g. ``["BTC", "USDT"]``).
        """
        params: dict[str, Any] = {}
        if currencies:
            params["ccy"] = ",".join(currencies)
        return await self._okx_request("GET", "/api/v5/account/balance", params=params)

    async def get_positions(
        self, *, inst_id: str | None = None, inst_type: str | None = None
    ) -> dict[str, Any]:
        """Get open positions.

        Args:
            inst_id: Filter by instrument.
            inst_type: Filter by instrument type.
        """
        params: dict[str, Any] = {}
        if inst_id is not None:
            params["instId"] = inst_id
        if inst_type is not None:
            params["instType"] = inst_type
        return await self._okx_request(
            "GET", "/api/v5/account/positions", params=params
        )

    # ------------------------------------------------------------------
    # Public endpoints (no auth)
    # ------------------------------------------------------------------

    async def get_instruments(
        self, inst_type: str = "SPOT", inst_id: str | None = None
    ) -> dict[str, Any]:
        """Get trading instruments info (public, no auth required)."""
        params: dict[str, Any] = {"instType": inst_type}
        if inst_id:
            params["instId"] = inst_id
        url = f"{self._base_url}/api/v5/public/instruments"
        resp = await self._http.get(url, params=params)
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result

    async def test_connectivity(self) -> bool:
        """Check if OKX API is reachable (public endpoint)."""
        try:
            resp = await self._http.get(f"{self._base_url}/api/v5/public/time")
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_order_params(body: dict[str, Any]) -> None:
        """Client-side validation before sending to OKX."""
        order_type = body.get("ordType", "")

        if order_type in ("limit", "post_only", "fok", "ioc"):
            if "px" not in body:
                raise InvalidOrderError(
                    f"{order_type} order requires 'price'", exchange="okx"
                )
