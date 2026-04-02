"""Settings endpoints with secure secret handling via OS keychain."""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.core.crypto import KeyPairManager
from app.core.dependencies import (
    AuthenticatedUser,
    build_response_meta,
    get_key_pair_manager,
    get_settings_service,
    optional_user,
)
from app.core.settings_service import SettingsService
from pnlclaw_security.secrets import SecretResolutionError
from pnlclaw_types.common import APIResponse
from pnlclaw_types.errors import ErrorCode, PnLClawError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


class ExchangeSettingsUpdate(BaseModel):
    provider: Literal["binance", "okx"] | None = None
    market_type: Literal["spot", "futures"] | None = None
    api_key: str | None = None
    api_secret: str | None = None
    clear_api_key: bool = False
    clear_api_secret: bool = False


class LLMSettingsUpdate(BaseModel):
    provider: str | None = None
    api_key: str | None = None
    clear_api_key: bool = False
    base_url: str | None = None
    model: str | None = None
    smart_mode: bool | None = None
    smart_models: dict[str, str] | None = None


class NetworkSettingsUpdate(BaseModel):
    proxy_url: str | None = None


class SettingsUpdateRequest(BaseModel):
    general: dict[str, Any] | None = Field(default=None)
    exchange: ExchangeSettingsUpdate | None = Field(default=None)
    llm: LLMSettingsUpdate | None = Field(default=None)
    risk: dict[str, Any] | None = Field(default=None)
    network: NetworkSettingsUpdate | None = Field(default=None)


@router.get("")
async def get_settings(
    request: Request,
    service: SettingsService = Depends(get_settings_service),
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[dict[str, Any]]:
    uid = user.id if user.id != "local" else None
    data = await service.get_settings(user_id=uid)
    return APIResponse(data=data, meta=build_response_meta(request), error=None)


@router.put("")
async def update_settings(
    request: Request,
    body: SettingsUpdateRequest,
    service: SettingsService = Depends(get_settings_service),
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[dict[str, Any]]:
    uid = user.id if user.id != "local" else None
    payload = body.model_dump(exclude_none=True)
    try:
        data = await service.update_settings(payload, user_id=uid)
    except SecretResolutionError as exc:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Secure secret storage is unavailable on this system",
            details={"reason": str(exc)},
        ) from exc

    if "llm" in payload:
        await _refresh_agent_runtime(service, user_id=uid)

    return APIResponse(data=data, meta=build_response_meta(request), error=None)


async def _refresh_agent_runtime(service: SettingsService, *, user_id: str | None = None) -> None:
    """Invalidate cached runtime so it will be rebuilt with new LLM settings."""
    import logging

    from app.api.v1.agent import invalidate_user_runtime

    log = logging.getLogger(__name__)
    invalidate_user_runtime(user_id)
    log.info("Invalidated agent runtime cache for user %s", user_id or "local")


@router.get("/public-key")
async def get_public_key(
    request: Request,
    manager: KeyPairManager = Depends(get_key_pair_manager),
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[dict[str, Any]]:
    """Return the ephemeral RSA public key (JWK) for encrypting secrets."""
    if manager is None:
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Encryption key pair is not available",
        )
    return APIResponse(
        data=manager.public_key_jwk(),
        meta=build_response_meta(request),
        error=None,
    )


@router.get("/llm/models")
async def list_llm_models(
    request: Request,
    service: SettingsService = Depends(get_settings_service),
    user: AuthenticatedUser = Depends(optional_user),
) -> APIResponse[dict[str, Any]]:
    """Fetch available models from the configured LLM provider."""
    import logging

    from pnlclaw_llm.base import LLMAuthError, LLMConfig, LLMConnectionError
    from pnlclaw_llm.openai_compat import OpenAICompatProvider

    log = logging.getLogger(__name__)

    uid = user.id if user.id != "local" else None
    llm_full = await service.resolve_llm_full_config(user_id=uid)

    api_key = llm_full.get("api_key")
    if not api_key:
        raise PnLClawError(
            code=ErrorCode.VALIDATION_ERROR,
            message="LLM API key not configured",
        )

    config = LLMConfig(
        model=llm_full.get("model") or "default",
        api_key=api_key,
        base_url=llm_full.get("base_url") or None,
    )

    provider = OpenAICompatProvider(config)
    try:
        models_data = await provider.list_models()
        seen: set[str] = set()
        models = []
        for m in models_data:
            mid = m.get("id", "")
            if mid and mid not in seen:
                seen.add(mid)
                models.append(
                    {
                        "id": mid,
                        "name": mid,
                        "owned_by": m.get("owned_by", ""),
                        "created": m.get("created", 0),
                    }
                )
        current_model = llm_full.get("model", "")
        return APIResponse(
            data={
                "models": models,
                "current_model": current_model,
                "total": len(models),
            },
            meta=build_response_meta(request),
            error=None,
        )
    except LLMAuthError as exc:
        log.warning("LLM authentication failed: %s", exc)
        raise PnLClawError(
            code=ErrorCode.AUTHENTICATION_ERROR,
            message="Invalid API key or authentication failed",
        ) from exc
    except LLMConnectionError as exc:
        log.warning("LLM connection failed: %s", exc)
        raise PnLClawError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="Failed to connect to LLM provider",
        ) from exc
    except Exception as exc:
        log.error("Failed to list models: %s", exc, exc_info=True)
        raise PnLClawError(
            code=ErrorCode.INTERNAL_ERROR,
            message="Failed to fetch models",
        ) from exc
    finally:
        await provider.close()
