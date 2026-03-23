"""PnLClaw Local API — FastAPI entrypoint with lifespan management."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.health import router as health_router
from app.api.v1.markets import router as markets_router
from app.api.v1.strategies import router as strategies_router
from app.api.v1.backtests import router as backtests_router
from app.api.v1.paper import router as paper_router
from app.api.v1.agent import router as agent_router
from app.api.v1.ws import router as ws_router
from app.middleware.error_handler import install_error_handlers
from app.middleware.request_id import RequestIDMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup and shutdown hooks.

    Startup: initialize WebSocket connections, load config, etc.
    Shutdown: close WS connections, flush logs, save state.
    """
    # --- Startup ---
    yield
    # --- Shutdown ---


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
    app.include_router(agent_router, prefix="/api/v1")
    app.include_router(ws_router)

    return app


app = create_app()
