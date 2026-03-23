"""Tests for pnlclaw_core.resilience.error_classifier."""

from pnlclaw_core.resilience.error_classifier import ErrorCategory, classify_error


class TestClassifyError:
    def test_timeout(self):
        assert classify_error(TimeoutError("timed out")) == ErrorCategory.TIMEOUT

    def test_asyncio_timeout(self):
        assert classify_error(TimeoutError()) == ErrorCategory.TIMEOUT

    def test_connection_error(self):
        assert classify_error(ConnectionError("refused")) == ErrorCategory.NETWORK

    def test_socket_error(self):
        assert classify_error(OSError("dns failure")) == ErrorCategory.NETWORK

    def test_rate_limit_429(self):
        assert classify_error(Exception("HTTP 429 Too Many Requests")) == ErrorCategory.RATE_LIMIT

    def test_rate_limit_text(self):
        assert classify_error(Exception("rate limit exceeded")) == ErrorCategory.RATE_LIMIT

    def test_auth_401(self):
        assert classify_error(Exception("HTTP 401 Unauthorized")) == ErrorCategory.AUTH

    def test_auth_forbidden(self):
        assert classify_error(Exception("403 Forbidden")) == ErrorCategory.AUTH

    def test_auth_invalid_key(self):
        assert classify_error(Exception("Invalid API key")) == ErrorCategory.AUTH

    def test_billing(self):
        assert classify_error(Exception("402 Payment Required")) == ErrorCategory.BILLING

    def test_billing_quota(self):
        assert classify_error(Exception("quota exceeded")) == ErrorCategory.BILLING

    def test_unknown(self):
        assert classify_error(ValueError("something else")) == ErrorCategory.UNKNOWN
