"""Tests for pnlclaw_security.guardrails.overtrading."""

import time

from pnlclaw_types import OrderSide, RiskLevel

from pnlclaw_security.guardrails.overtrading import (
    OvertradingConfig,
    OvertradingDetector,
)


class TestHourlyRate:
    def test_below_limit_no_alert(self) -> None:
        detector = OvertradingDetector(OvertradingConfig(max_orders_per_hour=5))
        now = time.time()
        for i in range(4):
            detector.record_order("BTC/USDT", OrderSide.BUY, timestamp=now - i)
        assert detector.check_hourly_rate(now=now) is None

    def test_at_limit_triggers(self) -> None:
        detector = OvertradingDetector(OvertradingConfig(max_orders_per_hour=5))
        now = time.time()
        for i in range(5):
            detector.record_order("BTC/USDT", OrderSide.BUY, timestamp=now - i)
        alert = detector.check_hourly_rate(now=now)
        assert alert is not None
        assert alert.rule == "hourly_rate"
        assert alert.severity == RiskLevel.RESTRICTED

    def test_old_orders_not_counted(self) -> None:
        detector = OvertradingDetector(OvertradingConfig(max_orders_per_hour=5))
        now = time.time()
        # Old orders (2 hours ago)
        for i in range(10):
            detector.record_order("BTC/USDT", OrderSide.BUY, timestamp=now - 7200 - i)
        # Recent orders
        for i in range(3):
            detector.record_order("BTC/USDT", OrderSide.BUY, timestamp=now - i)
        assert detector.check_hourly_rate(now=now) is None


class TestDailyRate:
    def test_below_limit_no_alert(self) -> None:
        detector = OvertradingDetector(OvertradingConfig(max_orders_per_day=10))
        now = time.time()
        for i in range(9):
            detector.record_order("BTC/USDT", OrderSide.BUY, timestamp=now - i * 100)
        assert detector.check_daily_rate(now=now) is None

    def test_at_limit_triggers(self) -> None:
        detector = OvertradingDetector(OvertradingConfig(max_orders_per_day=10))
        now = time.time()
        for i in range(10):
            detector.record_order("BTC/USDT", OrderSide.BUY, timestamp=now - i * 100)
        alert = detector.check_daily_rate(now=now)
        assert alert is not None
        assert alert.rule == "daily_rate"
        assert alert.severity == RiskLevel.DANGEROUS


class TestReversalDetection:
    def test_no_reversal_same_side(self) -> None:
        detector = OvertradingDetector(OvertradingConfig(max_reversals_per_hour=2))
        now = time.time()
        detector.record_order("BTC/USDT", OrderSide.BUY, timestamp=now - 60)
        detector.record_order("BTC/USDT", OrderSide.BUY, timestamp=now - 30)
        alert = detector.check_reversal("BTC/USDT", OrderSide.BUY, now=now)
        assert alert is None

    def test_reversal_detected(self) -> None:
        config = OvertradingConfig(max_reversals_per_hour=2, reversal_window_seconds=300)
        detector = OvertradingDetector(config)
        now = time.time()
        # BUY → SELL → BUY creates 2 reversals
        detector.record_order("BTC/USDT", OrderSide.BUY, timestamp=now - 120)
        detector.record_order("BTC/USDT", OrderSide.SELL, timestamp=now - 60)
        # Now checking if a BUY would create a 3rd reversal
        alert = detector.check_reversal("BTC/USDT", OrderSide.BUY, now=now)
        assert alert is not None
        assert alert.rule == "frequent_reversal"

    def test_different_symbols_not_counted(self) -> None:
        detector = OvertradingDetector(OvertradingConfig(max_reversals_per_hour=2))
        now = time.time()
        detector.record_order("BTC/USDT", OrderSide.BUY, timestamp=now - 60)
        detector.record_order("ETH/USDT", OrderSide.SELL, timestamp=now - 30)
        alert = detector.check_reversal("BTC/USDT", OrderSide.SELL, now=now)
        # Only 1 reversal on BTC/USDT, should not trigger with limit=2
        assert alert is None


class TestEvaluate:
    def test_multiple_alerts(self) -> None:
        config = OvertradingConfig(max_orders_per_hour=3, max_orders_per_day=5)
        detector = OvertradingDetector(config)
        now = time.time()
        for i in range(5):
            detector.record_order("BTC/USDT", OrderSide.BUY, timestamp=now - i)
        alerts = detector.evaluate("BTC/USDT", OrderSide.BUY, now=now)
        rules = {a.rule for a in alerts}
        assert "hourly_rate" in rules
        assert "daily_rate" in rules

    def test_no_alerts(self) -> None:
        detector = OvertradingDetector()
        now = time.time()
        detector.record_order("BTC/USDT", OrderSide.BUY, timestamp=now)
        alerts = detector.evaluate("BTC/USDT", OrderSide.BUY, now=now)
        assert alerts == []


class TestReset:
    def test_reset_clears_orders(self) -> None:
        detector = OvertradingDetector(OvertradingConfig(max_orders_per_hour=2))
        now = time.time()
        for i in range(5):
            detector.record_order("BTC/USDT", OrderSide.BUY, timestamp=now - i)
        assert detector.check_hourly_rate(now=now) is not None

        detector.reset()
        assert detector.check_hourly_rate(now=now) is None
