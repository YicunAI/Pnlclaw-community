"""Strategy CRUD and validation endpoints.

Strategies are stored in-memory for v0.1.  A persistent storage backend
(via ``pnlclaw_storage``) will be wired in a future sprint.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from app.core.dependencies import build_response_meta
from pnlclaw_types.common import APIResponse, Pagination
from pnlclaw_types.errors import NotFoundError
from pnlclaw_types.strategy import StrategyConfig, StrategyType

router = APIRouter(prefix="/strategies", tags=["strategies"])


# ---------------------------------------------------------------------------
# In-memory store (replaced by storage repository in S3-K03)
# ---------------------------------------------------------------------------

_strategies: dict[str, StrategyConfig] = {}


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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("")
async def create_strategy(
    request: Request,
    body: CreateStrategyRequest,
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
    )
    _strategies[strategy_id] = config
    return APIResponse(
        data=config.model_dump(),
        meta=build_response_meta(request),
        error=None,
    )


@router.get("")
async def list_strategies(
    request: Request,
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=1000, description="Page size"),
) -> APIResponse[list[dict[str, Any]]]:
    """List all strategies with pagination."""
    all_strategies = list(_strategies.values())
    total = len(all_strategies)
    page = all_strategies[offset : offset + limit]
    return APIResponse(
        data=[s.model_dump() for s in page],
        meta=build_response_meta(
            request,
            pagination=Pagination(offset=offset, limit=limit, total=total),
        ),
        error=None,
    )


@router.get("/{strategy_id}")
async def get_strategy(
    strategy_id: str,
    request: Request,
) -> APIResponse[dict[str, Any]]:
    """Get a strategy by ID."""
    config = _strategies.get(strategy_id)
    if config is None:
        raise NotFoundError(f"Strategy '{strategy_id}' not found")
    return APIResponse(
        data=config.model_dump(),
        meta=build_response_meta(request),
        error=None,
    )


@router.delete("/{strategy_id}")
async def delete_strategy(
    strategy_id: str,
    request: Request,
) -> APIResponse[dict[str, Any]]:
    """Delete a strategy by ID."""
    config = _strategies.pop(strategy_id, None)
    if config is None:
        raise NotFoundError(f"Strategy '{strategy_id}' not found")
    return APIResponse(
        data={"deleted": strategy_id},
        meta=build_response_meta(request),
        error=None,
    )


@router.post("/validate")
async def validate_strategy(
    request: Request,
    body: ValidateStrategyRequest,
) -> APIResponse[dict[str, Any]]:
    """Validate a strategy configuration without storing it.

    Attempts to load the config through ``pnlclaw_strategy.validator``
    if available, otherwise performs basic schema validation only.
    """
    # Build a temporary StrategyConfig for validation
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
        # strategy-engine not installed — schema validation only (already passed Pydantic)
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
