"""Tests for pnlclaw_core.diagnostics.health."""

import pytest

from pnlclaw_core.diagnostics.health import HealthCheckResult, HealthRegistry


class TestHealthRegistry:
    @pytest.mark.asyncio
    async def test_register_and_run(self):
        reg = HealthRegistry()

        async def check_db():
            return {"status": "healthy", "detail": "sqlite ok"}

        reg.register_check("db", check_db)
        results = await reg.run_all()
        assert len(results) == 1
        assert results[0].name == "db"
        assert results[0].status == "healthy"
        assert results[0].latency_ms >= 0

    @pytest.mark.asyncio
    async def test_unhealthy_on_exception(self):
        reg = HealthRegistry()

        async def bad_check():
            raise ConnectionError("db down")

        reg.register_check("db", bad_check)
        results = await reg.run_all()
        assert results[0].status == "unhealthy"
        assert "db down" in results[0].detail["error"]

    @pytest.mark.asyncio
    async def test_returns_health_check_result(self):
        reg = HealthRegistry()

        async def check():
            return HealthCheckResult(name="ws", status="degraded", latency_ms=0, detail={"lag": 5})

        reg.register_check("ws", check)
        results = await reg.run_all()
        assert results[0].status == "degraded"

    def test_check_names(self):
        reg = HealthRegistry()
        reg.register_check("a", lambda: None)
        reg.register_check("b", lambda: None)
        assert set(reg.check_names) == {"a", "b"}
