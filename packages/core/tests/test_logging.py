"""Tests for pnlclaw_core.logging."""

from pnlclaw_core.logging import (
    _redact_value,
    bind_request_id,
    get_request_id,
    setup_logging,
)


class TestRedaction:
    def test_openai_key(self):
        assert "sk-abc***" in _redact_value("key is sk-abcdef12345678")

    def test_bearer_token(self):
        result = _redact_value("Authorization: Bearer eyJabc123456789xyzabc")
        assert "***" in result
        # Should keep prefix and mask the rest
        assert "Bearer eyJab" in result

    def test_jwt(self):
        # Standalone JWT (not preceded by token=)
        result = _redact_value("jwt: eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig")
        assert "eyJhbGci***" in result

    def test_no_sensitive_data(self):
        plain = "normal log message about BTC/USDT"
        assert _redact_value(plain) == plain

    def test_password_field(self):
        result = _redact_value("password=MySecret123456")
        assert "MyS***" in result


class TestRequestId:
    def test_bind_and_get(self):
        bind_request_id("req-001")
        assert get_request_id() == "req-001"

    def test_default_none(self):
        # Reset by binding None-ish — but we test the default path
        from pnlclaw_core.logging import _request_id_var

        token = _request_id_var.set(None)
        assert get_request_id() is None
        _request_id_var.reset(token)


class TestSetupLogging:
    def test_setup_json(self):
        setup_logging(log_level="DEBUG", json_format=True)

    def test_setup_console(self):
        setup_logging(log_level="INFO", json_format=False)
