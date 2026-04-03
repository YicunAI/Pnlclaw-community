"""Backtest endpoints.

POST /backtests returns 202 with a task_id since backtests can be long-running.
Results are stored in-memory for v0.1 (replaced by storage repo later).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.core.dependencies import (
    AuthenticatedUser,
    build_response_meta,
    get_db_manager,
    get_market_service,
    optional_user,
)
from pnlclaw_types.common import APIResponse, Pagination
from pnlclaw_types.errors import NotFoundError
from pnlclaw_types.strategy import BacktestResult

logger = logging.getLogger(__name__)

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
    strategy_name: str = ""
    symbol: str = ""
    interval: str = "1h"
    status: BacktestTaskStatus = BacktestTaskStatus.PENDING
    result: BacktestResult | None = None
    user_id: str = "local"
    error: str | None = None
    created_at: int = Field(default_factory=lambda: int(time.time() * 1000))


_MAX_TASKS = 1000
_MAX_CONCURRENT_PER_USER = 10
_tasks: dict[str, BacktestTask] = {}

_result_owners: dict[str, str] = {}


def _evict_oldest_tasks() -> None:
    """Remove oldest tasks when exceeding limit."""
    while len(_tasks) > _MAX_TASKS:
        oldest_key = next(iter(_tasks))
        _tasks.pop(oldest_key, None)


def _get_results_store() -> dict[str, BacktestResult]:
    """Return the unified backtest results store (single source of truth)."""
    from pnlclaw_agent.tools.strategy_tools import get_results_store

    return get_results_store()


# ---------------------------------------------------------------------------
# Request body — accepts both frontend and canonical field names
# ---------------------------------------------------------------------------


class RunBacktestRequest(BaseModel):
    """Body for POST /backtests."""

    strategy_id: str = Field(..., description="Strategy to backtest")
    start_date: str | None = Field(None, description="Start date ISO-8601 (optional)")
    end_date: str | None = Field(None, description="End date ISO-8601 (optional)")
    initial_capital: float = Field(10_000.0, gt=0, alias="initial_capital", description="Starting capital")
    initial_cash: float | None = Field(None, gt=0, description="Starting capital (alias)")
    commission_rate: float = Field(0.001, ge=0, description="Commission rate")
    data_path: str | None = Field(None, description="Optional parquet data path")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Override strategy parameters")

    model_config = {"populate_by_name": True}

    @property
    def effective_cash(self) -> float:
        return self.initial_cash if self.initial_cash is not None else self.initial_capital


# ---------------------------------------------------------------------------
# Background runner — wired to real BacktestEngine
# ---------------------------------------------------------------------------


async def _run_backtest(task: BacktestTask, body: RunBacktestRequest) -> None:
    """Execute backtest in background using the real BacktestEngine."""
    task.status = BacktestTaskStatus.RUNNING
    try:
        from app.api.v1.strategies import _get_strategy
        from pnlclaw_backtest.commissions import PercentageCommission
        from pnlclaw_backtest.engine import BacktestConfig, BacktestEngine
        from pnlclaw_strategy.compiler import compile as compile_strategy
        from pnlclaw_strategy.models import EngineStrategyConfig
        from pnlclaw_strategy.runtime import StrategyRuntime

        config = await _get_strategy(body.strategy_id, user_id=task.user_id)
        if config is None:
            raise ValueError(f"Strategy '{body.strategy_id}' not found")

        task.strategy_name = config.name
        task.symbol = config.symbols[0] if config.symbols else ""
        task.interval = config.interval or "1h"

        engine_config = EngineStrategyConfig.model_validate(config.model_dump())

        # FX11: Parse string-format entry/exit rules into ConditionRule objects.
        # The AI strategy generator stores rules as strings like "EMA21 > EMA55"
        # but the compiler needs structured ConditionRule objects.
        from pnlclaw_strategy.rule_parser import parse_entry_rules, parse_exit_rules

        if not engine_config.parsed_entry_rules.long and not engine_config.parsed_entry_rules.short:
            if engine_config.entry_rules:
                parsed_entry = parse_entry_rules(engine_config.entry_rules)
                engine_config = engine_config.model_copy(update={"parsed_entry_rules": parsed_entry})
        if not engine_config.parsed_exit_rules.close_long and not engine_config.parsed_exit_rules.close_short:
            if engine_config.exit_rules:
                parsed_exit = parse_exit_rules(engine_config.exit_rules)
                engine_config = engine_config.model_copy(update={"parsed_exit_rules": parsed_exit})
        if engine_config.risk_params and engine_config.parsed_risk_params.stop_loss_pct is None:
            from pnlclaw_strategy.models import RiskParams

            try:
                parsed_rp = RiskParams.model_validate(engine_config.risk_params)
                engine_config = engine_config.model_copy(update={"parsed_risk_params": parsed_rp})
            except Exception:
                pass

        logger.info(
            "Backtest %s: parsed %d long + %d short entry rules, %d close_long + %d close_short exit rules",
            task.task_id,
            len(engine_config.parsed_entry_rules.long),
            len(engine_config.parsed_entry_rules.short),
            len(engine_config.parsed_exit_rules.close_long),
            len(engine_config.parsed_exit_rules.close_short),
        )

        # P8: Apply parameter overrides from request body
        if body.parameters:
            merged = {**engine_config.parameters, **body.parameters}
            engine_config = engine_config.model_copy(update={"parameters": merged})

        compiled = compile_strategy(engine_config)
        # FX06: Pass strategy direction to runtime
        from pnlclaw_types.strategy import StrategyDirection

        direction = getattr(config, "direction", StrategyDirection.LONG_ONLY)
        strategy = StrategyRuntime(compiled, direction=direction)

        kline_df = await _load_kline_data(config, body)

        # FX10: Apply date range filter with proper error reporting
        if body.start_date or body.end_date:
            if "timestamp" in kline_df.columns:
                if body.start_date:
                    try:
                        start_ts = int(pd.Timestamp(body.start_date).timestamp() * 1000)
                        kline_df = kline_df[kline_df["timestamp"] >= start_ts]
                    except (ValueError, TypeError) as exc:
                        raise ValueError(f"Invalid start_date format '{body.start_date}': {exc}") from exc
                if body.end_date:
                    try:
                        end_ts = int(pd.Timestamp(body.end_date).timestamp() * 1000)
                        kline_df = kline_df[kline_df["timestamp"] <= end_ts]
                    except (ValueError, TypeError) as exc:
                        raise ValueError(f"Invalid end_date format '{body.end_date}': {exc}") from exc

        bt_config = BacktestConfig(
            initial_cash=body.effective_cash,
            commission=PercentageCommission(rate=body.commission_rate),
            strategy_id=config.id,
            symbol=task.symbol,
            interval=task.interval,
        )
        engine = BacktestEngine(config=bt_config)

        result = await asyncio.to_thread(engine.run, strategy, kline_df)

        # FX05: Unify task_id and result.id so frontend can always look up by task_id
        result.id = task.task_id

        task.result = result
        task.status = BacktestTaskStatus.COMPLETED

        # Store in unified results cache
        from pnlclaw_agent.tools.strategy_tools import _evict_oldest_results

        _get_results_store()[result.id] = result
        _result_owners[result.id] = task.user_id
        _evict_oldest_results()

        db = get_db_manager()
        if db is not None:
            try:
                from pnlclaw_storage.repositories.backtests import BacktestRepository

                repo = BacktestRepository(db)
                await repo.save(result, user_id=task.user_id)
            except Exception:
                logger.warning("Failed to persist backtest result to DB", exc_info=True)
        else:
            logger.warning("No DB manager available — backtest result only in memory")

        logger.info(
            "Backtest %s completed: trades=%d, return=%.4f",
            task.task_id,
            result.trades_count,
            result.metrics.total_return,
        )

    except Exception as exc:
        logger.warning("Backtest %s failed: %s", task.task_id, exc, exc_info=True)
        task.error = str(exc)
        task.status = BacktestTaskStatus.FAILED


async def _load_kline_data(
    config: Any,
    body: RunBacktestRequest,
) -> pd.DataFrame:
    """Load kline data from explicit path, market service, or demo data."""
    if body.data_path:
        path = Path(body.data_path)
        if not path.is_absolute():
            path = Path.cwd() / path
        safe_root = Path.home() / ".pnlclaw" / "data"
        demo_root = Path.cwd() / "demo" / "data"
        try:
            resolved = path.resolve()
            if not (
                str(resolved).startswith(str(safe_root.resolve()))
                or str(resolved).startswith(str(demo_root.resolve()))
            ):
                raise PermissionError(f"data_path must be under {safe_root} or {demo_root}")
        except (OSError, ValueError) as exc:
            raise PermissionError(f"Invalid data_path: {exc}") from exc
        if path.exists() and path.suffix == ".parquet":
            return pd.read_parquet(path)
        raise FileNotFoundError(f"Data file not found: {body.data_path}")

    market_svc = get_market_service()
    symbol = config.symbols[0] if config.symbols else "BTC/USDT"
    if market_svc is not None:
        try:
            klines = await market_svc.fetch_klines_rest(
                symbol=symbol,
                interval=config.interval or "1h",
                limit=2000,
            )
            if klines:
                rows = [
                    {
                        "timestamp": k.timestamp,
                        "open": k.open,
                        "high": k.high,
                        "low": k.low,
                        "close": k.close,
                        "volume": k.volume,
                        "symbol": k.symbol,
                    }
                    for k in klines
                ]
                return pd.DataFrame(rows)
        except Exception:
            logger.debug("REST kline fetch failed, falling back to demo data", exc_info=True)

    demo_paths = [
        Path("demo/data/btc_usdt_1h_90d.parquet"),
        Path("demo/data/eth_usdt_1h_90d.parquet"),
    ]
    symbol_lower = symbol.lower().replace("/", "_")
    for dp in demo_paths:
        if symbol_lower in dp.name and dp.exists():
            return pd.read_parquet(dp)
    for dp in demo_paths:
        if dp.exists():
            return pd.read_parquet(dp)

    raise FileNotFoundError(
        f"No kline data available for {symbol}. Provide data_path or ensure the exchange is reachable."
    )


def _resolve_strategy_symbol_interval(strategy_id: str) -> tuple[str, str]:
    """Best-effort lookup of symbol/interval from strategy cache."""
    from app.api.v1.strategies import _strategies

    config = _strategies.get(strategy_id)
    if config is not None:
        symbol = config.symbols[0] if config.symbols else ""
        return symbol, config.interval or "1h"
    return "", "1h"


async def _ensure_strategies_loaded(user_id: str = "local") -> None:
    """Pre-warm _strategies cache from DB for a specific user."""
    from app.api.v1.strategies import _strategies

    try:
        from app.core.dependencies import get_strategy_repo

        repo = get_strategy_repo()
        if repo is not None:
            uid = user_id if user_id != "local" else None
            configs = await repo.list(limit=10000, offset=0, user_id=uid)
            for config in configs:
                _strategies[config.id] = config
    except Exception:
        logger.debug("Failed to pre-warm strategies cache", exc_info=True)


def _result_to_frontend_dict(result: BacktestResult) -> dict[str, Any]:
    """Convert persisted/shared backtest result to frontend-compatible dict."""
    m = result.metrics
    eq = result.equity_curve

    drawdown_curve = result.drawdown_curve
    if not drawdown_curve and len(eq) >= 2:
        import numpy as np

        arr = np.asarray(eq, dtype=np.float64)
        peak = np.maximum.accumulate(arr)
        dd = ((arr - peak) / peak).tolist()
        drawdown_curve = [round(v, 8) for v in dd]

    buy_hold_curve = result.buy_hold_curve
    if not buy_hold_curve and len(eq) >= 2:
        start_val = eq[0]
        end_val = eq[-1]
        ratio = end_val / start_val if start_val else 1.0
        buy_hold_curve = [round(start_val * (1 + (ratio - 1) * (i / (len(eq) - 1))), 2) for i in range(len(eq))]

    symbol = result.symbol
    interval = result.interval

    if not symbol or not interval:
        fallback_sym, fallback_int = _resolve_strategy_symbol_interval(result.strategy_id)
        symbol = symbol or fallback_sym
        interval = interval or fallback_int

    if not symbol and result.trades:
        for tr in result.trades:
            sym = tr.get("symbol") if isinstance(tr, dict) else getattr(tr, "symbol", None)
            if sym:
                symbol = sym
                break

    return {
        "id": result.id,
        "task_id": result.id,
        "strategy_id": result.strategy_id,
        "strategy_version": result.strategy_version,
        "strategy_name": result.strategy_id,
        "symbol": symbol,
        "interval": interval,
        "status": "completed",
        "created_at": result.created_at,
        "total_return": m.total_return,
        "annual_return": m.annual_return,
        "sharpe_ratio": m.sharpe_ratio,
        "max_drawdown": m.max_drawdown,
        "win_rate": m.win_rate,
        "profit_factor": m.profit_factor,
        "total_trades": m.total_trades,
        "calmar_ratio": m.calmar_ratio,
        "sortino_ratio": m.sortino_ratio,
        "expectancy": m.expectancy,
        "recovery_factor": m.recovery_factor,
        "equity_curve": eq,
        "drawdown_curve": drawdown_curve,
        "buy_hold_curve": buy_hold_curve,
        "trades": result.trades,
        "result": result.model_dump(mode="json"),
        "error": None,
    }


def _task_to_frontend_dict(task: BacktestTask) -> dict[str, Any]:
    """Convert task to frontend-compatible dict with flattened metrics."""
    data: dict[str, Any] = {
        "id": task.task_id,
        "task_id": task.task_id,
        "strategy_id": task.strategy_id,
        "strategy_name": task.strategy_name,
        "symbol": task.symbol,
        "interval": task.interval,
        "status": task.status.value,
        "created_at": task.created_at,
        "error": task.error,
    }
    if task.result is not None:
        result_data = _result_to_frontend_dict(task.result)
        result_data["id"] = task.task_id
        result_data["task_id"] = task.task_id
        if task.strategy_name:
            result_data["strategy_name"] = task.strategy_name
        if task.symbol:
            result_data["symbol"] = task.symbol
        if task.interval:
            result_data["interval"] = task.interval
        data.update(result_data)
    return data


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=202)
async def start_backtest(
    request: Request,
    body: RunBacktestRequest,
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[dict[str, Any]]:
    """Start a backtest (async).  Returns 202 with a task_id."""
    active_count = sum(
        1 for t in _tasks.values()
        if t.user_id == user.id and t.status in (BacktestTaskStatus.PENDING, BacktestTaskStatus.RUNNING)
    )
    if active_count >= _MAX_CONCURRENT_PER_USER:
        raise HTTPException(429, f"Too many active backtests ({_MAX_CONCURRENT_PER_USER} max)")

    task_id = f"bt-{uuid.uuid4().hex[:8]}"
    task = BacktestTask(task_id=task_id, strategy_id=body.strategy_id, user_id=user.id)
    _tasks[task_id] = task
    _evict_oldest_tasks()

    asyncio.create_task(_run_backtest(task, body))

    return APIResponse(
        data={"task_id": task_id, "status": task.status.value},
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/{task_id}")
async def get_backtest(
    task_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[dict[str, Any]]:
    """Get backtest task status and result (if completed)."""
    await _ensure_strategies_loaded(user.id)
    task = _tasks.get(task_id)
    if task is not None:
        if user.id != "local" and task.user_id != user.id:
            raise NotFoundError(f"Backtest task '{task_id}' not found")
        return APIResponse(
            data=_task_to_frontend_dict(task),
            meta=build_response_meta(request),
            error=None,
        )

    # Check unified results store
    cached = _get_results_store().get(task_id)
    if cached is not None:
        owner = _result_owners.get(task_id)
        if user.id != "local" and (owner is None or owner != user.id):
            raise NotFoundError(f"Backtest task '{task_id}' not found")
        return APIResponse(
            data=_result_to_frontend_dict(cached),
            meta=build_response_meta(request),
            error=None,
        )

    db = get_db_manager()
    if db is not None:
        try:
            from pnlclaw_storage.repositories.backtests import BacktestRepository

            repo = BacktestRepository(db)
            persisted = await repo.get(task_id, user_id=user.id)
            if persisted is not None:
                return APIResponse(
                    data=_result_to_frontend_dict(persisted),
                    meta=build_response_meta(request),
                    error=None,
                )
        except Exception:
            logger.debug("Persisted backtest lookup failed", exc_info=True)

    raise NotFoundError(f"Backtest task '{task_id}' not found")


@router.get("")
async def list_backtests(
    request: Request,
    strategy_id: str | None = Query(None, description="Filter by strategy ID"),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[list[dict[str, Any]]]:
    """List backtest tasks and persisted results, optionally filtered by strategy_id."""
    await _ensure_strategies_loaded(user.id)
    items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    tasks = list(_tasks.values())
    if user.id != "local":
        tasks = [t for t in tasks if t.user_id == user.id]
    if strategy_id is not None:
        tasks = [t for t in tasks if t.strategy_id == strategy_id]
    for task in tasks:
        payload = _task_to_frontend_dict(task)
        items.append(payload)
        seen_ids.add(str(payload["id"]))

    for result in _get_results_store().values():
        if strategy_id is not None and result.strategy_id != strategy_id:
            continue
        if result.id in seen_ids:
            continue
        owner = _result_owners.get(result.id)
        if user.id != "local" and (owner is None or owner != user.id):
            continue
        payload = _result_to_frontend_dict(result)
        items.append(payload)
        seen_ids.add(result.id)

    db = get_db_manager()
    if db is not None:
        try:
            from pnlclaw_storage.repositories.backtests import BacktestRepository

            repo = BacktestRepository(db)
            persisted = (
                await repo.list_by_strategy(strategy_id, limit=1000, user_id=user.id)
                if strategy_id is not None
                else await repo.list_all(limit=1000, offset=0, user_id=user.id)
            )
            for result in persisted:
                if result.id in seen_ids:
                    continue
                payload = _result_to_frontend_dict(result)
                items.append(payload)
                seen_ids.add(result.id)
        except Exception:
            logger.debug("Persisted backtest list lookup failed", exc_info=True)

    items.sort(key=lambda item: int(item.get("created_at", 0)), reverse=True)
    total = len(items)
    page = items[offset : offset + limit]

    return APIResponse(
        data=page,
        meta=build_response_meta(
            request,
            pagination=Pagination(offset=offset, limit=limit, total=total),
        ),
        error=None,
    )


@router.delete("/{backtest_id}")
async def delete_backtest(
    backtest_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[dict[str, Any]]:
    """Delete a backtest by ID (in-memory + persisted)."""
    # Ownership check for in-memory task
    task = _tasks.get(backtest_id)
    if task is not None and user.id != "local" and task.user_id != user.id:
        raise NotFoundError(f"Backtest '{backtest_id}' not found")

    owner = _result_owners.get(backtest_id)
    if owner is not None and user.id != "local" and owner != user.id:
        raise NotFoundError(f"Backtest '{backtest_id}' not found")

    _tasks.pop(backtest_id, None)
    _result_owners.pop(backtest_id, None)

    results_store = _get_results_store()
    results_store.pop(backtest_id, None)

    db = get_db_manager()
    if db is not None:
        try:
            from pnlclaw_storage.repositories.backtests import BacktestRepository

            repo = BacktestRepository(db)
            await repo.delete(backtest_id, user_id=user.id)
        except Exception:
            logger.debug("Persisted backtest delete failed", exc_info=True)

    return APIResponse(
        data={"deleted": backtest_id},
        meta=build_response_meta(request),
        error=None,
    )
