"""Tests for pnlclaw_types.errors — error hierarchy and HTTP status mapping."""

from pnlclaw_types.errors import (
    ERROR_CODE_HTTP_STATUS,
    ErrorCode,
    ExchangeError,
    InternalError,
    NotFoundError,
    PnLClawError,
    RateLimitedError,
    RiskDeniedError,
    ValidationError,
)


class TestErrorCode:
    def test_all_codes_have_http_mapping(self):
        """Every ErrorCode must have an HTTP status code mapping."""
        for code in ErrorCode:
            assert code in ERROR_CODE_HTTP_STATUS, f"{code} missing HTTP mapping"

    def test_http_status_values(self):
        assert ERROR_CODE_HTTP_STATUS[ErrorCode.VALIDATION_ERROR] == 400
        assert ERROR_CODE_HTTP_STATUS[ErrorCode.NOT_FOUND] == 404
        assert ERROR_CODE_HTTP_STATUS[ErrorCode.RISK_DENIED] == 403
        assert ERROR_CODE_HTTP_STATUS[ErrorCode.RATE_LIMITED] == 429
        assert ERROR_CODE_HTTP_STATUS[ErrorCode.EXCHANGE_ERROR] == 502
        assert ERROR_CODE_HTTP_STATUS[ErrorCode.INTERNAL_ERROR] == 500


class TestPnLClawError:
    def test_base_error(self):
        err = PnLClawError(ErrorCode.INTERNAL_ERROR, "Something broke")
        assert err.code == ErrorCode.INTERNAL_ERROR
        assert err.message == "Something broke"
        assert err.http_status == 500
        assert err.details is None

    def test_with_details(self):
        err = PnLClawError(
            ErrorCode.VALIDATION_ERROR,
            "Bad input",
            details={"field": "symbol"},
        )
        assert err.details == {"field": "symbol"}
        assert err.http_status == 400

    def test_to_dict(self):
        err = PnLClawError(
            ErrorCode.NOT_FOUND, "Not found", details={"id": "123"}
        )
        d = err.to_dict()
        assert d["code"] == "NOT_FOUND"
        assert d["message"] == "Not found"
        assert d["details"] == {"id": "123"}

    def test_to_dict_no_details(self):
        err = PnLClawError(ErrorCode.INTERNAL_ERROR, "Oops")
        d = err.to_dict()
        assert "details" not in d

    def test_is_exception(self):
        err = PnLClawError(ErrorCode.INTERNAL_ERROR, "fail")
        assert isinstance(err, Exception)


class TestSubclasses:
    def test_validation_error(self):
        err = ValidationError("Invalid symbol", {"field": "symbol"})
        assert err.code == ErrorCode.VALIDATION_ERROR
        assert err.http_status == 400
        assert isinstance(err, PnLClawError)

    def test_not_found_error(self):
        err = NotFoundError("Strategy not found")
        assert err.code == ErrorCode.NOT_FOUND
        assert err.http_status == 404

    def test_exchange_error(self):
        err = ExchangeError("Binance timeout")
        assert err.code == ErrorCode.EXCHANGE_ERROR
        assert err.http_status == 502

    def test_risk_denied_error(self):
        err = RiskDeniedError("Position too large")
        assert err.code == ErrorCode.RISK_DENIED
        assert err.http_status == 403

    def test_rate_limited_error(self):
        err = RateLimitedError("Too many requests")
        assert err.code == ErrorCode.RATE_LIMITED
        assert err.http_status == 429

    def test_internal_error(self):
        err = InternalError("Unexpected")
        assert err.code == ErrorCode.INTERNAL_ERROR
        assert err.http_status == 500
