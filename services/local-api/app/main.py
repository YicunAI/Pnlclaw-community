"""PnLClaw Local API — FastAPI entrypoint with lifespan management."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.agent import router as agent_router
from app.api.v1.backtests import router as backtests_router
from app.api.v1.health import router as health_router
from app.api.v1.markets import router as markets_router
from app.api.v1.paper import router as paper_router
from app.api.v1.strategies import router as strategies_router
from app.api.v1.trading import router as trading_router
from app.api.v1.ws import router as ws_router
from app.core.dependencies import (
    set_execution_engine,
    set_execution_mode,
    set_health_registry,
    set_market_service,
)
from app.middleware.error_handler import install_error_handlers
from app.middleware.request_id import RequestIDMiddleware
from pnlclaw_core.diagnostics.health import HealthCheckResult, HealthRegistry

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup and shutdown hooks."""
    from pnlclaw_market import MarketDataService

    # --- Health ---
    async def _local_api_health() -> HealthCheckResult:
        return HealthCheckResult(name="local_api", status="healthy", latency_ms=0.0)

    registry = HealthRegistry()
    registry.register_check("local_api", _local_api_health)
    set_health_registry(registry)

    # --- Market Data Service ---
    ws_url = os.environ.get(
        "PNLCLAW_BINANCE_WS_URL", "wss://data-stream.binance.vision/ws"
    )
    rest_url = os.environ.get(
        "PNLCLAW_BINANCE_REST_URL", "https://data-api.binance.vision/api/v3/depth"
    )
    default_interval = os.environ.get("PNLCLAW_DEFAULT_INTERVAL", "1h")

    market_svc = MarketDataService(
        ws_url=ws_url,
        rest_url=rest_url,
        kline_interval=default_interval,
    )

    try:
        await market_svc.start()
        set_market_service(market_svc)

        # Bridge EventBus → WS broadcast so that incoming exchange events
        # are pushed to connected WebSocket clients in real time.
        _bridge_market_events(market_svc)

        # Subscribe to default symbols from env (comma-separated)
        default_symbols = os.environ.get("PNLCLAW_DEFAULT_SYMBOLS", "")
        if default_symbols:
            for sym in default_symbols.split(","):
                sym = sym.strip()
                if sym:
                    try:
                        await market_svc.add_symbol(sym)
                        logger.info("Subscribed to default symbol: %s", sym)
                    except Exception:
                        logger.warning(
                            "Failed to subscribe to %s (exchange may be unreachable)",
                            sym, exc_info=True,
                        )

        # Register market health check
        async def _market_health() -> HealthCheckResult:
            running = market_svc.is_running
            syms = market_svc.get_symbols() if running else []
            return HealthCheckResult(
                name="market_data",
                status="healthy" if running else "degraded",
                latency_ms=0.0,
                detail={"running": running, "symbols": len(syms)},
            )

        registry.register_check("market_data", _market_health)

        # --- Execution Engine (Paper by default) ---
        from pnlclaw_paper.paper_execution import PaperExecutionEngine

        paper_engine = PaperExecutionEngine(
            initial_balance=float(
                os.environ.get("PNLCLAW_PAPER_BALANCE", "100000")
            ),
        )
        await paper_engine.start()
        set_execution_engine(paper_engine)
        set_execution_mode("paper")

        # Bridge price ticks from MarketDataService to PaperExecutionEngine
        _bridge_price_to_paper(market_svc, paper_engine)

        # Bridge execution events to trading WS
        _bridge_execution_events(paper_engine)

        logger.info("PnLClaw Local API started with MarketDataService + PaperExecutionEngine")
        yield

    finally:
        # --- Shutdown ---
        await paper_engine.stop()
        set_execution_engine(None)
        await market_svc.stop()
        set_market_service(None)
        logger.info("PnLClaw Local API shutdown complete")


def _bridge_market_events(market_svc: object) -> None:
    """Bridge MarketDataService EventBus events to WebSocket broadcast."""
    import asyncio

    from app.api.v1.ws import broadcast_market_event
    from pnlclaw_types.market import KlineEvent, OrderBookL2Snapshot, TickerEvent

    def _on_ticker(event: TickerEvent) -> None:
        asyncio.ensure_future(broadcast_market_event(
            event.symbol, "ticker", event.model_dump(),
        ))

    def _on_kline(event: KlineEvent) -> None:
        asyncio.ensure_future(broadcast_market_event(
            event.symbol, "kline", event.model_dump(),
        ))

    def _on_orderbook(event: OrderBookL2Snapshot) -> None:
        asyncio.ensure_future(broadcast_market_event(
            event.symbol, "depth", event.model_dump(),
        ))

    from pnlclaw_market import MarketDataService as _MDS

    svc: _MDS = market_svc  # type: ignore[assignment]
    svc.on_ticker(_on_ticker)
    svc.on_kline(_on_kline)
    svc.on_orderbook(_on_orderbook)


def _bridge_price_to_paper(market_svc: object, paper_engine: object) -> None:
    """Forward real-time ticker prices to PaperExecutionEngine for fill simulation."""
    import asyncio

    from pnlclaw_market import MarketDataService as _MDS
    from pnlclaw_paper.paper_execution import PaperExecutionEngine as _PE
    from pnlclaw_types.market import TickerEvent

    svc: _MDS = market_svc  # type: ignore[assignment]
    engine: _PE = paper_engine  # type: ignore[assignment]

    def _on_ticker_for_paper(event: TickerEvent) -> None:
        asyncio.ensure_future(engine.on_price_tick(event.symbol, event.last_price))

    svc.on_ticker(_on_ticker_for_paper)


def _bridge_execution_events(engine: object) -> None:
    """Bridge ExecutionEngine callbacks to the trading WebSocket broadcast."""
    import asyncio

    from app.api.v1.ws import broadcast_trading_event
    from pnlclaw_types.trading import BalanceUpdate, Fill, Order, Position

    def _on_order(order: Order) -> None:
        asyncio.ensure_future(broadcast_trading_event(
            "orders", "order_update", order.model_dump(),
        ))

    def _on_fill(fill: Fill) -> None:
        asyncio.ensure_future(broadcast_trading_event(
            "orders", "fill", fill.model_dump(),
        ))

    def _on_position(pos: Position) -> None:
        asyncio.ensure_future(broadcast_trading_event(
            "positions", "position_update", pos.model_dump(),
        ))

    def _on_balance(balances: list[BalanceUpdate]) -> None:
        asyncio.ensure_future(broadcast_trading_event(
            "balances", "balance_update", [b.model_dump() for b in balances],
        ))

    engine.on_order_update(_on_order)  # type: ignore[union-attr]
    engine.on_fill(_on_fill)  # type: ignore[union-attr]
    engine.on_position_update(_on_position)  # type: ignore[union-attr]
    engine.on_balance_update(_on_balance)  # type: ignore[union-attr]


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="PnLClaw Local API",
        description="Local-first crypto quantitative trading platform API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Middleware (outermost first)
    app.add_middleware(RequestIDMiddleware)

    # CORS — allow desktop frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "tauri://localhost"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Error handlers (must be installed before routers for catch-all to work)
    install_error_handlers(app)

    # Routers
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(markets_router, prefix="/api/v1")
    app.include_router(strategies_router, prefix="/api/v1")
    app.include_router(backtests_router, prefix="/api/v1")
    app.include_router(paper_router, prefix="/api/v1")
    app.include_router(trading_router, prefix="/api/v1")
    app.include_router(agent_router, prefix="/api/v1")
    app.include_router(ws_router)

    return app


app = create_app()
