"""Tests for pnlclaw_types.common — serialization/deserialization roundtrips."""

from pnlclaw_types.common import APIResponse, ErrorInfo, Pagination, ResponseMeta


class TestPagination:
    def test_defaults(self):
        p = Pagination()
        assert p.offset == 0
        assert p.limit == 50
        assert p.total == 0

    def test_roundtrip(self):
        p = Pagination(offset=10, limit=20, total=100)
        raw = p.model_dump_json()
        restored = Pagination.model_validate_json(raw)
        assert restored == p

    def test_from_dict(self):
        p = Pagination.model_validate({"offset": 5, "limit": 25, "total": 50})
        assert p.offset == 5


class TestErrorInfo:
    def test_roundtrip(self):
        e = ErrorInfo(
            code="VALIDATION_ERROR",
            message="Invalid symbol",
            details={"field": "symbol"},
        )
        raw = e.model_dump_json()
        restored = ErrorInfo.model_validate_json(raw)
        assert restored == e

    def test_details_optional(self):
        e = ErrorInfo(code="NOT_FOUND", message="Not found")
        assert e.details is None


class TestResponseMeta:
    def test_roundtrip(self):
        m = ResponseMeta(request_id="req-001", pagination=Pagination(total=10))
        raw = m.model_dump_json()
        restored = ResponseMeta.model_validate_json(raw)
        assert restored == m

    def test_all_optional(self):
        m = ResponseMeta()
        assert m.request_id is None
        assert m.pagination is None


class TestAPIResponse:
    def test_success_response(self):
        resp = APIResponse[dict](
            data={"price": 67000.0},
            meta=ResponseMeta(request_id="req-001"),
            error=None,
        )
        raw = resp.model_dump_json()
        restored = APIResponse[dict].model_validate_json(raw)
        assert restored.data == {"price": 67000.0}
        assert restored.error is None

    def test_error_response(self):
        resp = APIResponse[dict](
            data=None,
            meta=ResponseMeta(request_id="req-002"),
            error=ErrorInfo(code="INTERNAL", message="Something went wrong"),
        )
        raw = resp.model_dump_json()
        restored = APIResponse[dict].model_validate_json(raw)
        assert restored.data is None
        assert restored.error is not None
        assert restored.error.code == "INTERNAL"

    def test_has_data_meta_error_fields(self):
        """APIResponse must have data/meta/error fields per S1-A01 spec."""
        fields = set(APIResponse.model_fields.keys())
        assert {"data", "meta", "error"} == fields
