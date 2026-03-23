"""Dependency injection for service instances used by API routes.

Each service is created once at startup (via lifespan) and injected into
route handlers through FastAPI's ``Depends`` mechanism.  During testing the
instances can be overridden via ``app.dependency_overrides``.
"""

from __future__ import annotations

from typing import Any

from pnlclaw_core.diagnostics.health import HealthRegistry

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


# ---------------------------------------------------------------------------
# FastAPI dependency callables
# ---------------------------------------------------------------------------


def get_health_registry() -> HealthRegistry:
    """Return the global HealthRegistry instance."""
    if _health_registry is None:
        return HealthRegistry()
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
