"""Dependency injection for service instances used by API routes.

Each service is created once at startup (via lifespan) and injected into
route handlers through FastAPI's ``Depends`` mechanism.  During testing the
instances can be overridden via ``app.dependency_overrides``.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from pnlclaw_core.diagnostics.health import HealthCheckResult, HealthRegistry
from pnlclaw_types.common import Pagination, ResponseMeta
from pnlclaw_types.errors import ErrorCode, PnLClawError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JWT Manager holder (shared secret with admin-api)
# ---------------------------------------------------------------------------

_jwt_manager: Any | None = None
_auth_enabled: bool = False

_bearer_scheme = HTTPBearer(auto_error=False)


class AuthenticatedUser(BaseModel):
    """Represents an authenticated user extracted from a valid JWT."""
    id: str
    role: str = "user"


def set_jwt_manager(mgr: Any) -> None:
    global _jwt_manager, _auth_enabled
    _jwt_manager = mgr
    _auth_enabled = mgr is not None


def get_jwt_manager() -> Any:
    return _jwt_manager


async def require_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthenticatedUser:
    """Validate the Bearer JWT and return the authenticated user.

    When auth is disabled (Community mode), returns a default local user.
    """
    if not _auth_enabled:
        return AuthenticatedUser(id="local", role="admin")

    if creds is None or not creds.credentials:
        raise PnLClawError(
            code=ErrorCode.AUTHENTICATION_ERROR,
            message="Missing or invalid Bearer token",
        )

    try:
        payload = _jwt_manager.decode_access_token(creds.credentials)
    except Exception as exc:
        raise PnLClawError(
            code=ErrorCode.AUTHENTICATION_ERROR,
            message=f"Invalid token: {exc}",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise PnLClawError(
            code=ErrorCode.AUTHENTICATION_ERROR,
            message="Token missing user identity",
        )

    return AuthenticatedUser(id=user_id, role=payload.get("role", "user"))


async def optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthenticatedUser:
    """Extract user from Bearer JWT.

    Community mode (auth disabled): returns local/admin.
    Pro mode (auth enabled): requires a valid Bearer token — missing or
    invalid tokens are rejected with 401.  No silent fallback to local/admin.
    """
    if not _auth_enabled:
        return AuthenticatedUser(id="local", role="admin")

    if creds is None or not creds.credentials:
        raise PnLClawError(
            code=ErrorCode.AUTHENTICATION_ERROR,
            message="Authentication required",
        )

    try:
        payload = _jwt_manager.decode_access_token(creds.credentials)
        user_id = payload.get("sub")
        if not user_id:
            raise PnLClawError(
                code=ErrorCode.AUTHENTICATION_ERROR,
                message="Token missing user identity",
            )
        return AuthenticatedUser(
            id=user_id,
            role=payload.get("role", "user"),
        )
    except PnLClawError:
        raise
    except Exception as exc:
        raise PnLClawError(
            code=ErrorCode.AUTHENTICATION_ERROR,
            message=f"Invalid token: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# Singleton holders — populated during lifespan startup
# ---------------------------------------------------------------------------

_health_registry: HealthRegistry | None = None
_market_service: Any | None = None
_paper_account_manager: Any | None = None
_paper_order_manager: Any | None = None
_paper_position_manager: Any | None = None
_risk_engine: Any | None = None
_agent_runtime: Any | None = None
_execution_engine: Any | None = None
_live_engine: Any | None = None
_execution_mode: str = "paper"
_settings_service: Any | None = None
_key_pair_manager: Any | None = None
_mcp_registry: Any | None = None
_skill_registry: Any | None = None
_strategy_repo: Any | None = None
_db_manager: Any | None = None
_tool_catalog: Any | None = None
_funding_rate_fetcher: Any | None = None
_chat_session_repo: Any | None = None
_strategy_runner: Any | None = None


# ---------------------------------------------------------------------------
# Setters — called from lifespan
# ---------------------------------------------------------------------------


def set_health_registry(registry: HealthRegistry) -> None:
    global _health_registry
    _health_registry = registry


def set_market_service(svc: Any) -> None:
    global _market_service
    _market_service = svc


def set_paper_managers(
    accounts: Any,
    orders: Any,
    positions: Any,
) -> None:
    global _paper_account_manager, _paper_order_manager, _paper_position_manager
    _paper_account_manager = accounts
    _paper_order_manager = orders
    _paper_position_manager = positions


def set_risk_engine(engine: Any) -> None:
    global _risk_engine
    _risk_engine = engine


def set_agent_runtime(runtime: Any) -> None:
    global _agent_runtime
    _agent_runtime = runtime


def set_execution_engine(engine: Any) -> None:
    global _execution_engine
    _execution_engine = engine


def set_live_engine(engine: Any) -> None:
    global _live_engine
    _live_engine = engine


def set_execution_mode(mode: str) -> None:
    global _execution_mode
    _execution_mode = mode


def set_settings_service(service: Any) -> None:
    global _settings_service
    _settings_service = service


def set_key_pair_manager(manager: Any) -> None:
    global _key_pair_manager
    _key_pair_manager = manager


def set_mcp_registry(registry: Any) -> None:
    """Set the McpRegistry instance (called from lifespan)."""
    global _mcp_registry
    _mcp_registry = registry


def set_skill_registry(registry: Any) -> None:
    """Set the SkillRegistry instance (called from lifespan)."""
    global _skill_registry
    _skill_registry = registry


def set_strategy_repo(repo: Any) -> None:
    """Set the StrategyRepository instance (called from lifespan)."""
    global _strategy_repo
    _strategy_repo = repo


def set_db_manager(db: Any) -> None:
    """Set the AsyncSQLiteManager instance (called from lifespan)."""
    global _db_manager
    _db_manager = db


def set_tool_catalog(catalog: Any) -> None:
    """Set the ToolCatalog instance (called from lifespan)."""
    global _tool_catalog
    _tool_catalog = catalog


def set_funding_rate_fetcher(fetcher: Any) -> None:
    """Set the FundingRateFetcher instance (called from lifespan)."""
    global _funding_rate_fetcher
    _funding_rate_fetcher = fetcher


def set_chat_session_repo(repo: Any) -> None:
    """Set the ChatSessionRepository instance (called from lifespan)."""
    global _chat_session_repo
    _chat_session_repo = repo


def set_strategy_runner(runner: Any) -> None:
    """Set the StrategyRunner instance (called from lifespan)."""
    global _strategy_runner
    _strategy_runner = runner


def build_response_meta(
    request: Request,
    pagination: Pagination | None = None,
) -> ResponseMeta:
    """Build API response metadata with request correlation id."""
    request_id = getattr(request.state, "request_id", None)
    return ResponseMeta(request_id=request_id, pagination=pagination)


# ---------------------------------------------------------------------------
# FastAPI dependency callables
# ---------------------------------------------------------------------------


def get_health_registry() -> HealthRegistry:
    """Return the global HealthRegistry instance."""
    global _health_registry
    if _health_registry is None:
        registry = HealthRegistry()

        async def _local_api_health() -> HealthCheckResult:
            return HealthCheckResult(name="local_api", status="healthy", latency_ms=0.0)

        registry.register_check("local_api", _local_api_health)
        _health_registry = registry
    return _health_registry


def get_market_service() -> Any:
    """Return the MarketDataService instance (or None if unavailable)."""
    return _market_service


def get_paper_account_manager() -> Any:
    """Return the PaperAccountManager instance (or None)."""
    return _paper_account_manager


def get_paper_order_manager() -> Any:
    """Return the PaperOrderManager instance (or None)."""
    return _paper_order_manager


def get_paper_position_manager() -> Any:
    """Return the PaperPositionManager instance (or None)."""
    return _paper_position_manager


def get_risk_engine() -> Any:
    """Return the RiskEngine instance (or None)."""
    return _risk_engine


def get_agent_runtime() -> Any:
    """Return the AgentRuntime instance (or None)."""
    return _agent_runtime


def get_execution_engine() -> Any:
    """Return the current ExecutionEngine (Paper or Live)."""
    return _execution_engine


def get_live_engine() -> Any:
    """Return the LiveExecutionEngine (or None if not configured)."""
    return _live_engine


def get_execution_mode() -> str:
    """Return the current execution mode ('paper' or 'live')."""
    return _execution_mode


def get_settings_service() -> Any:
    """Return the SettingsService instance (or None)."""
    if _settings_service is None:
        from app.core.crypto import KeyPairManager
        from app.core.settings_service import SettingsService
        from pnlclaw_security.secrets import SecretManager

        return SettingsService(
            secret_manager=SecretManager(),
            key_pair_manager=_key_pair_manager,
        )
    return _settings_service


def get_key_pair_manager() -> Any:
    """Return the KeyPairManager instance (or None)."""
    return _key_pair_manager


def get_mcp_registry() -> Any:
    """Return the McpRegistry instance (or None)."""
    return _mcp_registry


def get_skill_registry() -> Any:
    """Return the SkillRegistry instance (or None)."""
    return _skill_registry


def get_strategy_repo() -> Any:
    """Return the StrategyRepository instance (or None)."""
    return _strategy_repo


def get_db_manager() -> Any:
    """Return the AsyncSQLiteManager instance (or None)."""
    return _db_manager


def get_tool_catalog() -> Any:
    """Return the ToolCatalog instance (or None)."""
    return _tool_catalog


def get_funding_rate_fetcher() -> Any:
    """Return the FundingRateFetcher instance (or None)."""
    return _funding_rate_fetcher


def get_chat_session_repo() -> Any:
    """Return the ChatSessionRepository instance (or None)."""
    return _chat_session_repo


def get_strategy_runner() -> Any:
    """Return the StrategyRunner instance (or None)."""
    return _strategy_runner
