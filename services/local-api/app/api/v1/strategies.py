"""Strategy CRUD and validation endpoints.

Strategies are stored in-memory and synced to SQLite via ``pnlclaw_storage``
when the storage layer is available. On startup, persisted strategies are
loaded into ``_strategies`` by the lifespan handler in ``main.py``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.core.dependencies import AuthenticatedUser, build_response_meta, get_strategy_repo, optional_user
from pnlclaw_types.common import APIResponse, Pagination
from pnlclaw_types.errors import NotFoundError
from pnlclaw_types.strategy import StrategyConfig, StrategyDeployment, StrategyType, StrategyVersionSnapshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strategies", tags=["strategies"])


# ---------------------------------------------------------------------------
# In-memory store — pre-loaded from DB at startup, synced on each mutation
# ---------------------------------------------------------------------------

_strategies: dict[str, StrategyConfig] = {}
_strategy_versions: dict[str, list[StrategyVersionSnapshot]] = {}
_strategy_deployments: list[StrategyDeployment] = []


async def _persist_save(config: StrategyConfig, *, user_id: str = "local") -> None:
    """Persist strategy to DB if repository is available."""
    repo = get_strategy_repo()
    if repo is not None:
        try:
            await repo.save(config, user_id=user_id)
        except Exception:
            logger.warning("Failed to persist strategy %s", config.id, exc_info=True)


async def _persist_delete(strategy_id: str, *, user_id: str = "local") -> None:
    """Delete strategy from DB if repository is available."""
    repo = get_strategy_repo()
    if repo is not None:
        try:
            await repo.delete(strategy_id, user_id=user_id)
        except Exception:
            logger.warning("Failed to delete strategy %s from DB", strategy_id, exc_info=True)


# ---------------------------------------------------------------------------
# Request / response bodies
# ---------------------------------------------------------------------------


class CreateStrategyRequest(BaseModel):
    """Body for POST /strategies."""

    name: str = Field(..., min_length=1, description="Strategy name")
    type: StrategyType = Field(..., description="Strategy archetype")
    description: str = Field("", description="Optional description")
    symbols: list[str] = Field(..., min_length=1, description="Trading pairs")
    interval: str = Field("1h", description="Kline interval")
    parameters: dict[str, Any] = Field(default_factory=dict)
    entry_rules: dict[str, Any] = Field(default_factory=dict)
    exit_rules: dict[str, Any] = Field(default_factory=dict)
    risk_params: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    source: str = Field("user")


class UpdateStrategyRequest(BaseModel):
    """Body for PUT /strategies/{id} — partial update."""

    name: str | None = Field(None, min_length=1)
    description: str | None = Field(None)
    symbols: list[str] | None = Field(None, min_length=1)
    interval: str | None = Field(None)
    parameters: dict[str, Any] | None = Field(None)
    entry_rules: dict[str, Any] | None = Field(None)
    exit_rules: dict[str, Any] | None = Field(None)
    risk_params: dict[str, Any] | None = Field(None)
    tags: list[str] | None = Field(None)
    source: str | None = Field(None)
    version_note: str | None = Field(None, description="Custom note for the version snapshot")


class DeployStrategyRequest(BaseModel):
    """Body for POST /strategies/{id}/deploy-paper."""

    account_id: str = Field("paper-default")


class ValidateStrategyRequest(BaseModel):
    """Body for POST /strategies/validate."""

    name: str = Field("untitled", min_length=1)
    type: StrategyType = Field(...)
    symbols: list[str] = Field(..., min_length=1)
    interval: str = Field("1h")
    parameters: dict[str, Any] = Field(default_factory=dict)
    entry_rules: dict[str, Any] = Field(default_factory=dict)
    exit_rules: dict[str, Any] = Field(default_factory=dict)
    risk_params: dict[str, Any] = Field(default_factory=dict)


async def _get_strategy(strategy_id: str, *, user_id: str = "local") -> StrategyConfig | None:
    """Load a strategy, preferring the repository when available."""
    repo = get_strategy_repo()
    if repo is not None:
        try:
            config = await repo.get(strategy_id, user_id=user_id)
            if config is not None:
                _strategies[strategy_id] = config
                return config
        except Exception:
            logger.debug("Failed to read strategy %s from repository", strategy_id, exc_info=True)
    return _strategies.get(strategy_id)


async def _list_strategies(
    *,
    offset: int,
    limit: int,
    tags: str | None,
    user_id: str = "local",
) -> list[StrategyConfig]:
    """List strategies, preferring repository-backed reads when available."""
    tag_list = [t.strip() for t in tags.split(",")] if tags else None
    repo = get_strategy_repo()
    if repo is not None:
        try:
            configs = await repo.list(limit=limit, offset=offset, tags=tag_list, user_id=user_id)
            for config in configs:
                _strategies[config.id] = config
            return configs
        except Exception:
            logger.debug("Failed to list strategies from repository", exc_info=True)

    configs = list(_strategies.values())
    if tags:
        tag_set = {t.strip().lower() for t in tags.split(",") if t.strip()}
        configs = [
            s for s in configs
            if tag_set & {t.lower() for t in getattr(s, "tags", [])}
        ]
    return configs[offset : offset + limit]


async def _save_version_snapshot(config: StrategyConfig, note: str) -> None:
    """Persist a version snapshot when storage is available."""
    snapshot = StrategyVersionSnapshot(
        id=f"sv-{uuid.uuid4().hex[:8]}",
        strategy_id=config.id,
        version=config.version,
        config_snapshot=config.model_dump(mode="json"),
        note=note,
        created_at=int(time.time() * 1000),
    )
    _strategy_versions.setdefault(config.id, []).append(snapshot)

    repo = get_strategy_repo()
    if repo is None or not hasattr(repo, "_db"):
        return
    try:
        from pnlclaw_storage.repositories.strategy_versions import StrategyVersionRepository

        version_repo = StrategyVersionRepository(repo._db)
        await version_repo.save(snapshot)
    except Exception:
        logger.debug("Failed to persist strategy version snapshot for %s", config.id, exc_info=True)


async def _list_version_snapshots(strategy_id: str) -> list[StrategyVersionSnapshot]:
    repo = get_strategy_repo()
    in_memory = list(reversed(_strategy_versions.get(strategy_id, [])))
    if repo is None or not hasattr(repo, "_db"):
        return in_memory
    try:
        from pnlclaw_storage.repositories.strategy_versions import StrategyVersionRepository

        persisted = await StrategyVersionRepository(repo._db).list_by_strategy(strategy_id)
        return persisted or in_memory
    except Exception:
        logger.debug("Failed to list strategy version snapshots for %s", strategy_id, exc_info=True)
        return in_memory


async def _persist_deployment_to_db(deployment: StrategyDeployment) -> None:
    repo = get_strategy_repo()
    if repo is None or not hasattr(repo, "_db"):
        return
    try:
        from pnlclaw_storage.repositories.strategy_versions import StrategyDeploymentRepository

        await StrategyDeploymentRepository(repo._db).save(deployment)
    except Exception:
        logger.debug("Failed to persist strategy deployment for %s", deployment.strategy_id, exc_info=True)


async def _save_deployment(deployment: StrategyDeployment) -> None:
    _strategy_deployments.append(deployment)
    await _persist_deployment_to_db(deployment)


async def _list_deployments(*, account_id: str | None = None) -> list[StrategyDeployment]:
    repo = get_strategy_repo()
    in_memory = list(reversed(_strategy_deployments))
    if account_id is not None:
        in_memory = [deployment for deployment in in_memory if deployment.account_id == account_id]
    if repo is None or not hasattr(repo, "_db"):
        return in_memory
    try:
        from pnlclaw_storage.repositories.strategy_versions import StrategyDeploymentRepository

        deployments: list[StrategyDeployment] = []
        for strategy_id in _strategies.keys():
            deployments.extend(await StrategyDeploymentRepository(repo._db).list_by_strategy(strategy_id))
        deployments.sort(key=lambda item: item.created_at, reverse=True)
        if account_id is not None:
            deployments = [deployment for deployment in deployments if deployment.account_id == account_id]
        return deployments or in_memory
    except Exception:
        logger.debug("Failed to list strategy deployments", exc_info=True)
        return in_memory


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("")
async def create_strategy(
    request: Request,
    body: CreateStrategyRequest,
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[dict[str, Any]]:
    """Create a new strategy and store it."""
    strategy_id = f"strat-{uuid.uuid4().hex[:8]}"
    config = StrategyConfig(
        id=strategy_id,
        name=body.name,
        type=body.type,
        description=body.description,
        symbols=body.symbols,
        interval=body.interval,
        parameters=body.parameters,
        entry_rules=body.entry_rules,
        exit_rules=body.exit_rules,
        risk_params=body.risk_params,
        tags=body.tags,
        source=body.source,
    )
    _strategies[strategy_id] = config
    asyncio.create_task(_persist_save(config, user_id=user.id))
    await _save_version_snapshot(config, "initial create")
    return APIResponse(
        data=_strategy_to_dict(config),
        meta=build_response_meta(request),
        error=None,
    )


def _strategy_to_dict(s: StrategyConfig) -> dict[str, Any]:
    """Convert strategy to dict with frontend-compatible fields."""
    d = s.model_dump()
    d["symbol"] = s.symbols[0] if s.symbols else ""
    return d


@router.get("")
async def list_strategies(
    request: Request,
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=1000, description="Page size"),
    tags: str | None = Query(None, description="Comma-separated tags to filter by"),
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[list[dict[str, Any]]]:
    """List all strategies with pagination and optional tag filtering."""
    repo = get_strategy_repo()
    if repo is not None:
        try:
            total = len(await repo.list(limit=10000, offset=0, tags=[t.strip() for t in tags.split(",")] if tags else None, user_id=user.id))
        except Exception:
            total = len(_strategies)
    else:
        all_strategies = list(_strategies.values())
        if tags:
            tag_set = {t.strip().lower() for t in tags.split(",") if t.strip()}
            all_strategies = [
                s for s in all_strategies
                if tag_set & {t.lower() for t in getattr(s, "tags", [])}
            ]
        total = len(all_strategies)

    page = await _list_strategies(offset=offset, limit=limit, tags=tags, user_id=user.id)
    return APIResponse(
        data=[_strategy_to_dict(s) for s in page],
        meta=build_response_meta(
            request,
            pagination=Pagination(offset=offset, limit=limit, total=total),
        ),
        error=None,
    )


# FX04: Static routes MUST be defined before parameterized /{strategy_id}
# to prevent FastAPI from matching "validate" or "deployments" as a strategy ID.

@router.post("/validate")
async def validate_strategy(
    request: Request,
    body: ValidateStrategyRequest,
) -> APIResponse[dict[str, Any]]:
    """Validate a strategy configuration without storing it.

    Attempts to load the config through ``pnlclaw_strategy.validator``
    if available, otherwise performs basic schema validation only.
    """
    tmp_id = f"tmp-{uuid.uuid4().hex[:8]}"
    config = StrategyConfig(
        id=tmp_id,
        name=body.name,
        type=body.type,
        symbols=body.symbols,
        interval=body.interval,
        parameters=body.parameters,
        entry_rules=body.entry_rules,
        exit_rules=body.exit_rules,
        risk_params=body.risk_params,
    )

    errors: list[str] = []
    try:
        from pnlclaw_strategy.models import EngineStrategyConfig
        from pnlclaw_strategy.validator import validate

        engine_config = EngineStrategyConfig.model_validate(config.model_dump())
        result = validate(engine_config)
        if not result.valid:
            errors = list(result.errors)
    except ImportError:
        pass
    except Exception as exc:
        errors.append(str(exc))

    return APIResponse(
        data={
            "valid": len(errors) == 0,
            "errors": errors,
        },
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/deployments/list")
async def list_strategy_deployments(
    request: Request,
    account_id: str | None = Query(None),
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[list[dict[str, Any]]]:
    """List strategy deployments, optionally filtered by paper account.

    In Pro mode, only returns deployments for strategies owned by the user.
    """
    deployments = await _list_deployments(account_id=account_id)
    if user.id != "local":
        user_strategy_ids: set[str] = set()
        repo = get_strategy_repo()
        if repo is not None:
            try:
                configs = await repo.list(limit=10000, offset=0, user_id=user.id)
                user_strategy_ids = {c.id for c in configs}
            except Exception:
                pass
        if not user_strategy_ids:
            user_strategy_ids = {sid for sid, cfg in _strategies.items()}
        deployments = [d for d in deployments if d.strategy_id in user_strategy_ids]
    return APIResponse(
        data=[deployment.model_dump(mode="json") for deployment in deployments],
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/runner/status")
async def get_runner_status(request: Request) -> APIResponse[dict[str, Any]]:
    """Get the status of the strategy runner and all active deployments."""
    from app.core.dependencies import get_strategy_runner

    runner = get_strategy_runner()
    if runner is None:
        return APIResponse(
            data={"running": False, "deployments": []},
            meta=build_response_meta(request),
            error=None,
        )

    slots = []
    for dep_id in runner.active_deployments:
        status = runner.get_slot_status(dep_id)
        if status:
            slots.append(status)

    return APIResponse(
        data={
            "running": runner.is_running,
            "deployment_count": len(slots),
            "deployments": slots,
        },
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/runner/{deployment_id}/signals")
async def get_deployment_signals(
    deployment_id: str,
    request: Request,
) -> APIResponse[dict[str, Any]]:
    """Get signal history for a specific deployment."""
    from app.core.dependencies import get_strategy_runner

    runner = get_strategy_runner()
    if runner is None:
        raise NotFoundError("Strategy runner not available")

    signals = runner.get_signal_history(deployment_id)
    status = runner.get_slot_status(deployment_id)

    return APIResponse(
        data={
            "deployment_id": deployment_id,
            "signals": signals,
            "total": len(signals),
            "status": status,
        },
        meta=build_response_meta(request),
        error=None,
    )


# --- Parameterized routes below ---

@router.get("/{strategy_id}")
async def get_strategy(
    strategy_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[dict[str, Any]]:
    """Get a strategy by ID."""
    config = await _get_strategy(strategy_id, user_id=user.id)
    if config is None:
        raise NotFoundError(f"Strategy '{strategy_id}' not found")
    return APIResponse(
        data=_strategy_to_dict(config),
        meta=build_response_meta(request),
        error=None,
    )


@router.put("/{strategy_id}")
async def update_strategy(
    strategy_id: str,
    body: UpdateStrategyRequest,
    request: Request,
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[dict[str, Any]]:
    """Update a strategy by ID (partial update)."""
    config = await _get_strategy(strategy_id, user_id=user.id)
    if config is None:
        raise NotFoundError(f"Strategy '{strategy_id}' not found")

    version_note = body.version_note
    update_data = body.model_dump(exclude_none=True)
    update_data.pop("version_note", None)
    if not update_data:
        return APIResponse(
            data=_strategy_to_dict(config),
            meta=build_response_meta(request),
            error=None,
        )

    update_data["version"] = config.version + 1
    updated = config.model_copy(update=update_data)
    _strategies[strategy_id] = updated
    asyncio.create_task(_persist_save(updated, user_id=user.id))
    await _save_version_snapshot(updated, version_note or "manual update")
    return APIResponse(
        data=_strategy_to_dict(updated),
        meta=build_response_meta(request),
        error=None,
    )




@router.get("/{strategy_id}/versions")
async def list_strategy_versions(
    strategy_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[list[dict[str, Any]]]:
    """List version snapshots with aggregated backtest metrics per version."""
    config = await _get_strategy(strategy_id, user_id=user.id)
    if config is None:
        raise NotFoundError(f"Strategy '{strategy_id}' not found")
    snapshots = await _list_version_snapshots(strategy_id)

    version_backtests: dict[int, list[dict[str, Any]]] = {}

    def _add_bt(bt_id: str, sid: str, ver: int, metrics: Any, trades: int, created: Any) -> None:
        version_backtests.setdefault(ver, []).append({
            "id": bt_id,
            "total_return": getattr(metrics, "total_return", 0),
            "sharpe_ratio": getattr(metrics, "sharpe_ratio", 0),
            "max_drawdown": getattr(metrics, "max_drawdown", 0),
            "win_rate": getattr(metrics, "win_rate", 0),
            "trades_count": trades,
            "created_at": created,
        })

    try:
        from app.api.v1.backtests import _result_owners
        from pnlclaw_agent.tools.strategy_tools import get_results_store
        for bt in get_results_store().values():
            if bt.strategy_id != strategy_id:
                continue
            owner = _result_owners.get(bt.id)
            if user.id != "local" and owner is not None and owner != user.id:
                continue
            _add_bt(bt.id, bt.strategy_id, bt.strategy_version, bt.metrics, bt.trades_count, bt.created_at)
    except Exception:
        pass

    seen_ids = {bt["id"] for bts in version_backtests.values() for bt in bts}
    try:
        from app.core.dependencies import get_db_manager
        from pnlclaw_storage.repositories.backtests import BacktestRepository
        db = get_db_manager()
        if db is not None:
            repo = BacktestRepository(db)
            persisted = await repo.list_by_strategy(strategy_id, limit=200, user_id=user.id)
            for bt in persisted:
                if bt.id not in seen_ids:
                    _add_bt(bt.id, bt.strategy_id, bt.strategy_version, bt.metrics, bt.trades_count, bt.created_at)
    except Exception:
        pass

    enriched = []
    for snap in snapshots:
        d = snap.model_dump(mode="json")
        d["backtests"] = version_backtests.get(snap.version, [])
        enriched.append(d)

    return APIResponse(
        data=enriched,
        meta=build_response_meta(request),
        error=None,
    )


@router.post("/{strategy_id}/confirm")
async def confirm_strategy(
    strategy_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[dict[str, Any]]:
    """Move a strategy to CONFIRMED state."""
    config = await _get_strategy(strategy_id, user_id=user.id)
    if config is None:
        raise NotFoundError(f"Strategy '{strategy_id}' not found")
    updated = config.model_copy(update={"lifecycle_state": "confirmed", "version": config.version + 1})
    _strategies[strategy_id] = updated
    asyncio.create_task(_persist_save(updated, user_id=user.id))
    await _save_version_snapshot(updated, "confirmed for paper deployment")
    return APIResponse(data=_strategy_to_dict(updated), meta=build_response_meta(request), error=None)


@router.post("/{strategy_id}/deploy-paper")
async def deploy_strategy_to_paper(
    strategy_id: str,
    body: DeployStrategyRequest,
    request: Request,
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[dict[str, Any]]:
    """Create a paper deployment and start continuous strategy execution.

    A dedicated strategy paper account is automatically created for each
    deployment. The StrategyRunner handles account creation, rule validation,
    duplicate prevention, and historical kline warmup internally.
    """
    config = await _get_strategy(strategy_id, user_id=user.id)
    if config is None:
        raise NotFoundError(f"Strategy '{strategy_id}' not found")
    if config.lifecycle_state not in ("confirmed", "draft", "running"):
        raise NotFoundError("Strategy must be in draft, confirmed, or running state to deploy")

    has_rules = bool(config.entry_rules) or bool(config.exit_rules)
    if not has_rules:
        return APIResponse(
            data={
                "deployment": None,
                "strategy": _strategy_to_dict(config),
                "runner_status": "failed",
                "runner_error": (
                    "Cannot deploy: strategy has no trading rules. "
                    "entry_rules and exit_rules are both empty. "
                    "Use AI to generate strategy logic or add rules manually first."
                ),
                "created_account": None,
            },
            meta=build_response_meta(request),
            error=None,
        )

    existing_running = next(
        (d for d in _strategy_deployments
         if d.strategy_id == strategy_id and d.status == "running"),
        None,
    )
    if existing_running:
        return APIResponse(
            data={
                "deployment": existing_running.model_dump(mode="json"),
                "strategy": _strategy_to_dict(config),
                "runner_status": "running",
                "runner_error": None,
                "already_deployed": True,
            },
            meta=build_response_meta(request),
            error=None,
        )

    deployment_id = f"dep-{uuid.uuid4().hex[:8]}"

    # StrategyRunner.deploy handles: account creation, compilation,
    # warmup, and duplicate prevention internally.
    account_id = body.account_id
    runner_error = None
    try:
        from app.core.dependencies import get_strategy_runner
        runner = get_strategy_runner()
        if runner is not None:
            runner_error = await runner.deploy(
                deployment_id=deployment_id,
                strategy_config=config.model_dump(),
                account_id=account_id,
            )
            if runner_error:
                logger.warning("Runner deploy failed: %s", runner_error)
        else:
            runner_error = "Strategy runner not initialized"
    except Exception as exc:
        runner_error = str(exc)
        logger.warning("Failed to start runner for deployment %s: %s", deployment_id, exc)

    if runner_error:
        return APIResponse(
            data={
                "deployment": None,
                "strategy": _strategy_to_dict(config),
                "runner_status": "failed",
                "runner_error": runner_error,
                "created_account": None,
            },
            meta=build_response_meta(request),
            error=None,
        )

    # Read back the actual account_id chosen by the runner
    slot_status = runner.get_slot_status(deployment_id) if runner else None
    actual_account_id = slot_status["account_id"] if slot_status else account_id

    # Register ownership so the account is visible only to this user
    try:
        from app.api.v1.paper import _register_owner
        _register_owner(actual_account_id, user.id)
    except Exception:
        logger.debug("Failed to register deployment account ownership", exc_info=True)

    deployment = StrategyDeployment(
        id=deployment_id,
        strategy_id=strategy_id,
        strategy_version=config.version,
        account_id=actual_account_id,
        mode="paper",
        status="running",
        created_at=int(time.time() * 1000),
    )
    _strategy_deployments.append(deployment)
    asyncio.create_task(_persist_deployment_to_db(deployment))

    if config.lifecycle_state != "running":
        updated = config.model_copy(update={"lifecycle_state": "running"})
        _strategies[strategy_id] = updated
        asyncio.create_task(_persist_save(updated, user_id=user.id))
    else:
        updated = config

    return APIResponse(
        data={
            "deployment": deployment.model_dump(mode="json"),
            "strategy": _strategy_to_dict(updated),
            "runner_status": "running",
            "runner_error": None,
            "created_account": None,
            "bar_count": slot_status.get("bar_count", 0) if slot_status else 0,
        },
        meta=build_response_meta(request),
        error=None,
    )


@router.post("/{strategy_id}/stop-deployment")
async def stop_strategy_deployment(
    strategy_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[dict[str, Any]]:
    """Stop a running strategy deployment."""
    from app.core.dependencies import get_strategy_runner

    runner = get_strategy_runner()

    stopped_in_runner: list[str] = []
    if runner is not None:
        stopped_in_runner = runner.stop_by_strategy_id(strategy_id)

    for dep in list(_strategy_deployments):
        if dep.strategy_id == strategy_id and dep.status == "running":
            dep.status = "stopped"

    config = await _get_strategy(strategy_id, user_id=user.id)
    if config is not None and config.lifecycle_state == "running":
        updated = config.model_copy(update={"lifecycle_state": "confirmed"})
        _strategies[strategy_id] = updated
        asyncio.create_task(_persist_save(updated, user_id=user.id))

    logger.info(
        "Stopped strategy %s: %d runner slot(s) removed",
        strategy_id, len(stopped_in_runner),
    )

    return APIResponse(
        data={"stopped_deployments": stopped_in_runner},
        meta=build_response_meta(request),
        error=None,
    )


@router.delete("/{strategy_id}")
async def delete_strategy(
    strategy_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[dict[str, Any]]:
    """Delete a strategy by ID."""
    config = _strategies.pop(strategy_id, None)
    if config is None:
        raise NotFoundError(f"Strategy '{strategy_id}' not found")
    asyncio.create_task(_persist_delete(strategy_id, user_id=user.id))
    return APIResponse(
        data={"deleted": strategy_id},
        meta=build_response_meta(request),
        error=None,
    )


