"""Tests for pnlclaw_core.resilience.backoff."""

from pnlclaw_core.resilience.backoff import BackoffPolicy


class TestBackoffPolicy:
    def test_defaults(self):
        p = BackoffPolicy()
        assert p.initial == 1.0
        assert p.max_delay == 60.0
        assert p.factor == 2.0
        assert p.jitter is True

    def test_exponential_growth_no_jitter(self):
        p = BackoffPolicy(initial=1.0, factor=2.0, jitter=False)
        assert p.calculate_delay(0) == 1.0
        assert p.calculate_delay(1) == 2.0
        assert p.calculate_delay(2) == 4.0
        assert p.calculate_delay(3) == 8.0

    def test_max_delay_cap(self):
        p = BackoffPolicy(initial=1.0, factor=2.0, max_delay=5.0, jitter=False)
        assert p.calculate_delay(10) == 5.0

    def test_jitter_within_range(self):
        p = BackoffPolicy(initial=10.0, factor=1.0, jitter=True)
        for _ in range(50):
            delay = p.calculate_delay(0)
            assert 7.5 <= delay <= 12.5  # 10 * [0.75, 1.25]

    def test_custom_params(self):
        p = BackoffPolicy(initial=0.5, max_delay=30.0, factor=3.0, jitter=False)
        assert p.calculate_delay(0) == 0.5
        assert p.calculate_delay(1) == 1.5
        assert p.calculate_delay(2) == 4.5
