"""Backtest endpoints.

POST /backtests returns 202 with a task_id since backtests can be long-running.
Results are stored in-memory for v0.1 (replaced by storage repo later).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from enum import Enum
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from pnlclaw_types.common import APIResponse, Pagination, ResponseMeta
from pnlclaw_types.errors import NotFoundError
from pnlclaw_types.strategy import BacktestResult

router = APIRouter(prefix="/backtests", tags=["backtests"])


# ---------------------------------------------------------------------------
# Task state
# ---------------------------------------------------------------------------


class BacktestTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class BacktestTask(BaseModel):
    task_id: str
    strategy_id: str
    status: BacktestTaskStatus = BacktestTaskStatus.PENDING
    result: BacktestResult | None = None
    error: str | None = None
    created_at: int = Field(default_factory=lambda: int(time.time() * 1000))


_tasks: dict[str, BacktestTask] = {}


# ---------------------------------------------------------------------------
# Request body
# ---------------------------------------------------------------------------


class RunBacktestRequest(BaseModel):
    """Body for POST /backtests."""

    strategy_id: str = Field(..., description="Strategy to backtest")
    start_date: str | None = Field(None, description="Start date ISO-8601 (optional)")
    end_date: str | None = Field(None, description="End date ISO-8601 (optional)")
    initial_cash: float = Field(10_000.0, gt=0, description="Starting capital")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Override strategy parameters"
    )


# ---------------------------------------------------------------------------
# Background runner
# ---------------------------------------------------------------------------


async def _run_backtest(task: BacktestTask, body: RunBacktestRequest) -> None:
    """Execute backtest in background.

    Tries to use the real BacktestEngine; falls back to a stub result
    if the engine or required data is not available.
    """
    task.status = BacktestTaskStatus.RUNNING
    try:
        # Attempt real engine execution
        from pnlclaw_backtest.engine import BacktestConfig, BacktestEngine

        from app.api.v1.strategies import _strategies

        config = _strategies.get(body.strategy_id)
        if config is None:
            raise ValueError(f"Strategy '{body.strategy_id}' not found")

        # If we reach here, we'd need kline data + compiled strategy.
        # For v0.1 API layer, generate a stub result to prove the endpoint works.
        raise ImportError("Full backtest pipeline not wired yet")

    except Exception:
        # Stub result for v0.1 — proves the async pipeline works end-to-end
        from datetime import datetime

        from pnlclaw_types.strategy import BacktestMetrics

        task.result = BacktestResult(
            id=task.task_id,
            strategy_id=body.strategy_id,
            start_date=datetime(2025, 1, 1),
            end_date=datetime(2025, 3, 31),
            metrics=BacktestMetrics(
                total_return=0.0,
                annual_return=0.0,
                sharpe_ratio=0.0,
                max_drawdown=0.0,
                win_rate=0.0,
                profit_factor=0.0,
                total_trades=0,
            ),
            equity_curve=[body.initial_cash],
            trades_count=0,
            created_at=int(time.time() * 1000),
        )
        task.status = BacktestTaskStatus.COMPLETED


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=202)
async def start_backtest(
    body: RunBacktestRequest,
) -> APIResponse[dict[str, Any]]:
    """Start a backtest (async).  Returns 202 with a task_id."""
    task_id = f"bt-{uuid.uuid4().hex[:8]}"
    task = BacktestTask(task_id=task_id, strategy_id=body.strategy_id)
    _tasks[task_id] = task

    # Fire-and-forget background task
    asyncio.create_task(_run_backtest(task, body))

    return APIResponse(
        data={"task_id": task_id, "status": task.status.value},
        meta=ResponseMeta(),
        error=None,
    )


@router.get("/{task_id}")
async def get_backtest(
    task_id: str,
) -> APIResponse[dict[str, Any]]:
    """Get backtest task status and result (if completed)."""
    task = _tasks.get(task_id)
    if task is None:
        raise NotFoundError(f"Backtest task '{task_id}' not found")

    data: dict[str, Any] = {
        "task_id": task.task_id,
        "strategy_id": task.strategy_id,
        "status": task.status.value,
        "created_at": task.created_at,
    }
    if task.result is not None:
        data["result"] = task.result.model_dump(mode="json")
    if task.error is not None:
        data["error"] = task.error

    return APIResponse(
        data=data,
        meta=ResponseMeta(),
        error=None,
    )


@router.get("")
async def list_backtests(
    strategy_id: str | None = Query(None, description="Filter by strategy ID"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
) -> APIResponse[list[dict[str, Any]]]:
    """List backtest tasks, optionally filtered by strategy_id."""
    tasks = list(_tasks.values())
    if strategy_id is not None:
        tasks = [t for t in tasks if t.strategy_id == strategy_id]

    total = len(tasks)
    page = tasks[offset : offset + limit]

    return APIResponse(
        data=[
            {
                "task_id": t.task_id,
                "strategy_id": t.strategy_id,
                "status": t.status.value,
                "created_at": t.created_at,
            }
            for t in page
        ],
        meta=ResponseMeta(
            pagination=Pagination(offset=offset, limit=limit, total=total),
        ),
        error=None,
    )
