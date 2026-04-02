"""Health check registry: register checks, run all, report results."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class HealthCheckResult:
    """Result of a single health check."""

    name: str
    status: str  # "healthy" | "unhealthy" | "degraded"
    latency_ms: float
    detail: dict[str, Any] | None = None


HealthCheckFn = Callable[[], Awaitable[HealthCheckResult | dict[str, Any]]]


class HealthRegistry:
    """Registry for health check functions.

    Health checks are async callables that return status information.
    ``run_all`` executes all registered checks and returns a list of results.
    """

    def __init__(self) -> None:
        self._checks: dict[str, HealthCheckFn] = {}

    def register_check(self, name: str, fn: HealthCheckFn) -> None:
        """Register a health check function.

        Args:
            name: Check name (e.g. 'binance_ws', 'sqlite', 'llm_provider').
            fn: Async callable that returns health status.
        """
        self._checks[name] = fn

    async def run_all(self) -> list[HealthCheckResult]:
        """Execute all registered health checks and return results."""
        results: list[HealthCheckResult] = []
        for name, fn in self._checks.items():
            start = time.monotonic()
            try:
                raw = await fn()
                latency = (time.monotonic() - start) * 1000
                if isinstance(raw, HealthCheckResult):
                    raw.latency_ms = latency
                    results.append(raw)
                elif isinstance(raw, dict):
                    results.append(
                        HealthCheckResult(
                            name=name,
                            status=raw.get("status", "healthy"),
                            latency_ms=latency,
                            detail=raw,
                        )
                    )
                else:
                    results.append(HealthCheckResult(name=name, status="healthy", latency_ms=latency))
            except Exception as exc:
                latency = (time.monotonic() - start) * 1000
                results.append(
                    HealthCheckResult(
                        name=name,
                        status="unhealthy",
                        latency_ms=latency,
                        detail={"error": str(exc)},
                    )
                )
        return results

    @property
    def check_names(self) -> list[str]:
        """List registered check names."""
        return list(self._checks.keys())
