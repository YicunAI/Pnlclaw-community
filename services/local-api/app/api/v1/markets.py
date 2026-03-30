"""Market data endpoints.

Provides ticker, kline, and L2 orderbook data for subscribed symbols
via the ``MarketDataService`` from ``pnlclaw_market``.

Supports multiple exchange sources (Binance spot/futures, OKX spot/futures)
selected via query parameters.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from app.core.dependencies import (
    build_response_meta,
    get_market_service,
    get_settings_service,
)
from app.core.settings_service import SettingsService
from pnlclaw_types.common import APIResponse
from pnlclaw_types.errors import ErrorCode, NotFoundError, PnLClawError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/markets", tags=["markets"])

_ALLOWED_EXCHANGES = {"binance", "okx"}
_ALLOWED_MARKET_TYPES = {"spot", "futures"}


def _normalize_symbol(raw: str) -> str:
    """Normalize URL-friendly symbol to internal format.

    Accepts ``BTCUSDT``, ``BTC-USDT``, ``btc_usdt``, ``BTC/USDT`` etc.
    and returns the internal format (passed as-is to MarketDataService,
    which uses the format registered at subscription time).
    """
    for sep in ("-", "_"):
        if sep in raw:
            return raw.replace(sep, "/").upper()
    return raw


def _resolve_source(
    exchange: str | None,
    market_type: str | None,
    settings_service: SettingsService,
) -> tuple[str, str]:
    """Determine (exchange, market_type) from query params or persisted settings."""
    settings = settings_service._load_non_sensitive()
    exchange_settings = settings.get("exchange", {}) if isinstance(settings, dict) else {}

    resolved_exchange = (exchange or str(exchange_settings.get("provider", "binance"))).strip().lower()
    resolved_market_type = (market_type or str(exchange_settings.get("market_type", "spot"))).strip().lower()

    if resolved_exchange not in _ALLOWED_EXCHANGES:
        raise PnLClawError(
            code=ErrorCode.INVALID_PARAMETER,
            message=f"Invalid exchange '{resolved_exchange}', expected one of: {', '.join(sorted(_ALLOWED_EXCHANGES))}",
        )

    if resolved_market_type not in _ALLOWED_MARKET_TYPES:
        raise PnLClawError(
            code=ErrorCode.INVALID_PARAMETER,
            message=f"Invalid market_type '{resolved_market_type}', expected one of: {', '.join(sorted(_ALLOWED_MARKET_TYPES))}",
        )

    return resolved_exchange, resolved_market_type


def _require_market_service(svc: Any = Depends(get_market_service)) -> Any:
    """Raise 503 if MarketDataService is not available."""
    if svc is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Market data service is not available",
        )
    return svc


async def _ensure_subscribed(
    svc: Any,
    symbol: str,
    exchange: str,
    market_type: str,
) -> None:
    """Auto-subscribe to a symbol on first access if not yet subscribed."""
    source = svc.get_source(exchange, market_type)
    if source is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message=f"No data source registered for {exchange}/{market_type}",
        )
    if symbol not in source.get_symbols():
        try:
            await svc.add_symbol(symbol, exchange=exchange, market_type=market_type)
        except Exception:
            logger.debug(
                "Auto-subscribe add_symbol failed for %s on %s/%s",
                symbol,
                exchange,
                market_type,
                exc_info=True,
            )


@router.get("")
async def list_symbols(
    request: Request,
    exchange: str | None = Query(None, description="Exchange provider"),
    market_type: str | None = Query(None, description="Market type"),
    svc: Any = Depends(_require_market_service),
    settings_service: SettingsService = Depends(get_settings_service),
) -> APIResponse[dict[str, Any]]:
    """List all currently subscribed symbols for a given source."""
    ex, mt = _resolve_source(exchange, market_type, settings_service)
    symbols: list[str] = svc.get_symbols(ex, mt)
    return APIResponse(
        data={"symbols": symbols, "count": len(symbols), "exchange": ex, "market_type": mt},
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/{symbol:path}/ticker")
async def get_ticker(
    symbol: str,
    request: Request,
    exchange: str | None = Query(None, description="Exchange provider: binance or okx"),
    market_type: str | None = Query(None, description="Market type: spot or futures"),
    svc: Any = Depends(_require_market_service),
    settings_service: SettingsService = Depends(get_settings_service),
) -> APIResponse[dict[str, Any]]:
    """Get the latest ticker for *symbol*."""
    sym = _normalize_symbol(symbol)
    ex, mt = _resolve_source(exchange, market_type, settings_service)
    await _ensure_subscribed(svc, sym, ex, mt)
    ticker = svc.get_ticker(sym, ex, mt)
    if ticker is None:
        raise NotFoundError(f"No ticker data for symbol '{sym}' on {ex}/{mt}")
    return APIResponse(
        data=ticker.model_dump(),
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/{symbol:path}/kline")
async def get_kline(
    symbol: str,
    request: Request,
    interval: str = Query("1h", description="Kline interval, e.g. 1m, 5m, 15m, 30m, 1h, 4h, 1d"),
    limit: int = Query(200, ge=1, le=1500, description="Max number of klines"),
    end_time: int | None = Query(None, description="Fetch candles before this timestamp (ms) for pagination"),
    exchange: str | None = Query(None, description="Exchange provider: binance or okx"),
    market_type: str | None = Query(None, description="Market type: spot or futures"),
    svc: Any = Depends(_require_market_service),
    settings_service: SettingsService = Depends(get_settings_service),
) -> APIResponse[dict[str, Any]]:
    """Get K-line (candlestick) data for *symbol*.

    Fetches from exchange REST API with the requested interval, ensuring
    multi-timeframe support regardless of the WS subscription interval.

    Pass ``end_time`` (ms) to paginate backwards into history.
    """
    sym = _normalize_symbol(symbol)
    ex, mt = _resolve_source(exchange, market_type, settings_service)
    await _ensure_subscribed(svc, sym, ex, mt)

    klines = await svc.fetch_klines_rest(sym, ex, mt, interval=interval, limit=limit, end_time=end_time)
    if not klines:
        raise NotFoundError(f"No kline data for symbol '{sym}' on {ex}/{mt}")

    return APIResponse(
        data={
            "symbol": sym,
            "interval": interval,
            "exchange": ex,
            "market_type": mt,
            "klines": [k.model_dump() for k in klines],
        },
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/{symbol:path}/orderbook")
async def get_orderbook(
    symbol: str,
    request: Request,
    depth: int = Query(20, ge=1, le=100, description="Orderbook depth (number of levels)"),
    exchange: str | None = Query(None, description="Exchange provider: binance or okx"),
    market_type: str | None = Query(None, description="Market type: spot or futures"),
    svc: Any = Depends(_require_market_service),
    settings_service: SettingsService = Depends(get_settings_service),
) -> APIResponse[dict[str, Any]]:
    """Get L2 orderbook snapshot for *symbol*."""
    sym = _normalize_symbol(symbol)
    ex, mt = _resolve_source(exchange, market_type, settings_service)
    await _ensure_subscribed(svc, sym, ex, mt)
    book = svc.get_orderbook(sym, ex, mt)
    if book is None:
        raise NotFoundError(f"No orderbook data for symbol '{sym}' on {ex}/{mt}")
    data = book.model_dump()
    data["bids"] = data["bids"][:depth]
    data["asks"] = data["asks"][:depth]
    return APIResponse(
        data=data,
        meta=build_response_meta(request),
        error=None,
    )
