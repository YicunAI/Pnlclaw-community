"""Tests for pnlclaw_core.diagnostics.metrics."""

from pnlclaw_core.diagnostics.metrics import MetricsCollector, MetricType


class TestMetricsCollector:
    def test_counter_increment(self):
        mc = MetricsCollector()
        mc.register("pnlclaw.market.ticks", MetricType.COUNTER, "Tick count")
        mc.increment("pnlclaw.market.ticks")
        mc.increment("pnlclaw.market.ticks", 5)
        assert mc.get_value("pnlclaw.market.ticks") == 6.0

    def test_gauge_set(self):
        mc = MetricsCollector()
        mc.register("pnlclaw.order.open_count", MetricType.GAUGE)
        mc.set("pnlclaw.order.open_count", 42)
        assert mc.get_value("pnlclaw.order.open_count") == 42

    def test_histogram_observe(self):
        mc = MetricsCollector()
        mc.register("pnlclaw.llm.latency_ms", MetricType.HISTOGRAM)
        mc.observe("pnlclaw.llm.latency_ms", 100)
        mc.observe("pnlclaw.llm.latency_ms", 200)
        values = mc.get_value("pnlclaw.llm.latency_ms")
        assert values == [100, 200]

    def test_labels(self):
        mc = MetricsCollector()
        mc.register("pnlclaw.market.ws_messages", MetricType.COUNTER)
        mc.increment("pnlclaw.market.ws_messages", labels={"exchange": "binance"})
        mc.increment("pnlclaw.market.ws_messages", labels={"exchange": "okx"})
        mc.increment("pnlclaw.market.ws_messages", labels={"exchange": "binance"}, value=2)
        assert mc.get_value("pnlclaw.market.ws_messages", labels={"exchange": "binance"}) == 3
        assert mc.get_value("pnlclaw.market.ws_messages", labels={"exchange": "okx"}) == 1

    def test_snapshot(self):
        mc = MetricsCollector()
        mc.register("m1", MetricType.COUNTER, "desc")
        mc.increment("m1")
        snap = mc.snapshot()
        assert "m1" in snap
        assert snap["m1"]["type"] == "counter"

    def test_unregistered_metric_noop(self):
        mc = MetricsCollector()
        mc.increment("nonexistent")  # Should not raise
        assert mc.get_value("nonexistent") is None
