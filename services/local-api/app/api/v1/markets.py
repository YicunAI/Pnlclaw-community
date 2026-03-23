"""Market data endpoints.

Provides ticker, kline, and L2 orderbook data for subscribed symbols
via the ``MarketDataService`` from ``pnlclaw_market``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from app.core.dependencies import build_response_meta, get_market_service
from pnlclaw_types.common import APIResponse
from pnlclaw_types.errors import ErrorCode, NotFoundError, PnLClawError

router = APIRouter(prefix="/markets", tags=["markets"])


def _normalize_symbol(raw: str) -> str:
    """Normalize URL-friendly symbol to internal format.

    Accepts ``BTCUSDT``, ``BTC-USDT``, ``btc_usdt``, ``BTC/USDT`` etc.
    and returns the internal format (passed as-is to MarketDataService,
    which uses the format registered at subscription time).
    """
    # Replace common URL-friendly separators with /
    for sep in ("-", "_"):
        if sep in raw:
            return raw.replace(sep, "/").upper()
    return raw


def _require_market_service(svc: Any = Depends(get_market_service)) -> Any:
    """Raise 503 if MarketDataService is not available."""
    if svc is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Market data service is not available",
        )
    return svc


@router.get("")
async def list_symbols(
    request: Request,
    svc: Any = Depends(_require_market_service),
) -> APIResponse[dict[str, Any]]:
    """List all currently subscribed symbols."""
    symbols: list[str] = svc.get_symbols()
    return APIResponse(
        data={"symbols": symbols, "count": len(symbols)},
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/{symbol}/ticker")
async def get_ticker(
    symbol: str,
    request: Request,
    svc: Any = Depends(_require_market_service),
) -> APIResponse[dict[str, Any]]:
    """Get the latest ticker for *symbol*.

    Symbol can be passed URL-friendly: ``BTC-USDT`` or ``BTCUSDT``.
    """
    sym = _normalize_symbol(symbol)
    ticker = svc.get_ticker(sym)
    if ticker is None:
        raise NotFoundError(f"No ticker data for symbol '{sym}'")
    return APIResponse(
        data=ticker.model_dump(),
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/{symbol}/kline")
async def get_kline(
    symbol: str,
    request: Request,
    interval: str = Query("1h", description="Kline interval, e.g. 1m, 1h, 1d"),
    limit: int = Query(100, ge=1, le=1000, description="Max number of klines"),
    svc: Any = Depends(_require_market_service),
) -> APIResponse[dict[str, Any]]:
    """Get K-line (candlestick) data for *symbol*.

    Currently returns the latest cached kline for the symbol.  Historical
    kline batching will be supported in a future release.
    """
    sym = _normalize_symbol(symbol)
    kline = svc.get_kline(sym)
    if kline is None:
        raise NotFoundError(f"No kline data for symbol '{sym}'")
    return APIResponse(
        data={
            "symbol": sym,
            "interval": interval,
            "klines": [kline.model_dump()],
        },
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/{symbol}/orderbook")
async def get_orderbook(
    symbol: str,
    request: Request,
    depth: int = Query(20, ge=1, le=100, description="Orderbook depth (number of levels)"),
    svc: Any = Depends(_require_market_service),
) -> APIResponse[dict[str, Any]]:
    """Get L2 orderbook snapshot for *symbol*."""
    sym = _normalize_symbol(symbol)
    book = svc.get_orderbook(sym)
    if book is None:
        raise NotFoundError(f"No orderbook data for symbol '{sym}'")
    data = book.model_dump()
    # Truncate to requested depth
    data["bids"] = data["bids"][:depth]
    data["asks"] = data["asks"][:depth]
    return APIResponse(
        data=data,
        meta=build_response_meta(request),
        error=None,
    )
