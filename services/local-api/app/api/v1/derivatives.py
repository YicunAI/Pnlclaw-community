"""Derivatives data endpoints — funding rate, open interest, liquidation stats.

Provides real-time derivatives analytics sourced from exchange WebSocket
streams and aggregated by the market-data aggregators.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from app.core.dependencies import build_response_meta, get_market_service
from pnlclaw_types.common import APIResponse
from pnlclaw_types.errors import ErrorCode, PnLClawError

router = APIRouter(prefix="/derivatives", tags=["derivatives"])


def _require_market_service(svc: Any = Depends(get_market_service)) -> Any:
    if svc is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Market data service is not available",
        )
    return svc


@router.get("/liquidation-stats")
async def get_liquidation_stats(
    request: Request,
    window: str = Query("1h", description="Time window: 15m, 30m, 1h, 4h, 24h"),
    svc: Any = Depends(_require_market_service),
) -> APIResponse[dict[str, Any]]:
    """Get aggregated liquidation statistics for a time window."""
    liq_agg = getattr(svc, "_liquidation_aggregator", None)
    if liq_agg is None:
        return APIResponse(
            data={"window": window, "message": "Liquidation aggregator not initialized"},
            meta=build_response_meta(request),
            error=None,
        )
    stats = liq_agg.get_stats(window)
    if stats is None:
        return APIResponse(
            data={"window": window, "total_liquidated_usd": 0, "long_count": 0, "short_count": 0},
            meta=build_response_meta(request),
            error=None,
        )
    return APIResponse(
        data=stats.model_dump(),
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/liquidation-stats/all")
async def get_all_liquidation_stats(
    request: Request,
    svc: Any = Depends(_require_market_service),
) -> APIResponse[dict[str, Any]]:
    """Get liquidation statistics for all time windows at once."""
    liq_agg = getattr(svc, "_liquidation_aggregator", None)
    if liq_agg is None:
        return APIResponse(
            data={"windows": {}},
            meta=build_response_meta(request),
            error=None,
        )
    all_stats = liq_agg.get_all_stats()
    return APIResponse(
        data={"windows": {k: v.model_dump() for k, v in all_stats.items()}},
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/liquidations/recent")
async def get_recent_liquidations(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    svc: Any = Depends(_require_market_service),
) -> APIResponse[dict[str, Any]]:
    """Get recent raw liquidation events."""
    liq_agg = getattr(svc, "_liquidation_aggregator", None)
    if liq_agg is None:
        return APIResponse(
            data={"events": [], "count": 0},
            meta=build_response_meta(request),
            error=None,
        )
    events = liq_agg.get_recent_events(limit)
    return APIResponse(
        data={
            "events": [e.model_dump() for e in events],
            "count": len(events),
        },
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/large-trades/recent")
async def get_recent_large_trades(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    svc: Any = Depends(_require_market_service),
) -> APIResponse[dict[str, Any]]:
    """Get recent large trades above threshold."""
    detector = getattr(svc, "_large_trade_detector", None)
    if detector is None:
        return APIResponse(
            data={"events": [], "count": 0},
            meta=build_response_meta(request),
            error=None,
        )
    events = detector.get_recent(limit)
    return APIResponse(
        data={
            "events": [e.model_dump() for e in events],
            "count": len(events),
            "threshold_usd": detector.threshold_usd,
        },
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/large-trades/stats")
async def get_large_trade_stats(
    request: Request,
    window_ms: int = Query(3_600_000, description="Time window in milliseconds"),
    svc: Any = Depends(_require_market_service),
) -> APIResponse[dict[str, Any]]:
    """Get large trade summary statistics."""
    detector = getattr(svc, "_large_trade_detector", None)
    if detector is None:
        return APIResponse(
            data={"message": "Large trade detector not initialized"},
            meta=build_response_meta(request),
            error=None,
        )
    stats = detector.get_stats(window_ms)
    return APIResponse(
        data=stats,
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/funding-rates")
async def get_funding_rates(
    request: Request,
    svc: Any = Depends(_require_market_service),
) -> APIResponse[dict[str, Any]]:
    """Get current funding rates for all tracked symbols (WS-based)."""
    store = getattr(svc, "_funding_rate_store", None)
    if store is None:
        return APIResponse(
            data={"rates": {}},
            meta=build_response_meta(request),
            error=None,
        )
    return APIResponse(
        data={"rates": {k: v.model_dump() for k, v in store.items()}},
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/funding-rates/all-exchanges")
async def get_all_exchange_funding_rates(
    request: Request,
    exchange: str = Query("all", description="Exchange filter: all, binance, okx"),
    force: bool = Query(False, description="Force refresh (bypass cache)"),
) -> APIResponse[dict[str, Any]]:
    """Get ALL funding rates from Binance and OKX (REST bulk fetch, cached)."""
    from app.core.dependencies import get_funding_rate_fetcher

    fetcher = get_funding_rate_fetcher()
    if fetcher is None:
        return APIResponse(
            data={"rates": [], "count": 0, "exchanges": []},
            meta=build_response_meta(request),
            error=None,
        )

    items = await fetcher.get_all(force=force)

    if exchange != "all":
        items = [it for it in items if it.exchange == exchange]

    return APIResponse(
        data={
            "rates": [it.to_dict() for it in items],
            "count": len(items),
            "exchanges": list({it.exchange for it in items}),
        },
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/open-interest")
async def get_open_interest(
    request: Request,
    svc: Any = Depends(_require_market_service),
) -> APIResponse[dict[str, Any]]:
    """Get current open interest for all tracked symbols."""
    store = getattr(svc, "_open_interest_store", None)
    if store is None:
        return APIResponse(
            data={"snapshots": {}},
            meta=build_response_meta(request),
            error=None,
        )
    return APIResponse(
        data={"snapshots": {k: v.model_dump() for k, v in store.items()}},
        meta=build_response_meta(request),
        error=None,
    )
