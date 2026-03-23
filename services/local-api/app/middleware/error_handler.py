"""Unified error handling middleware.

Catches all exceptions and returns consistent JSON error responses.
Integrates with PnLClawError hierarchy from shared-types.
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from pnlclaw_types.errors import ERROR_CODE_HTTP_STATUS, ErrorCode, PnLClawError

logger = structlog.get_logger(__name__)


def install_error_handlers(app: FastAPI) -> None:
    """Register exception handlers on the FastAPI application."""

    @app.exception_handler(PnLClawError)
    async def _handle_pnlclaw_error(
        request: Request, exc: PnLClawError
    ) -> JSONResponse:
        """Map PnLClawError to the correct HTTP status with unified body."""
        status = ERROR_CODE_HTTP_STATUS.get(exc.code, exc.http_status)
        body = {
            "data": None,
            "meta": {"request_id": getattr(request.state, "request_id", None)},
            "error": exc.to_dict(),
        }
        logger.warning(
            "pnlclaw_error",
            code=exc.code.value,
            message=exc.message,
            status=status,
        )
        return JSONResponse(status_code=status, content=body)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Pydantic / FastAPI validation errors → 422."""
        details = [
            {
                "loc": list(e.get("loc", [])),
                "msg": e.get("msg", ""),
                "type": e.get("type", ""),
            }
            for e in exc.errors()
        ]
        body = {
            "data": None,
            "meta": {"request_id": getattr(request.state, "request_id", None)},
            "error": {
                "code": ErrorCode.VALIDATION_ERROR.value,
                "message": "Request validation failed",
                "details": {"errors": details},
            },
        }
        return JSONResponse(status_code=422, content=body)

    @app.exception_handler(Exception)
    async def _handle_unknown_error(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Catch-all for unhandled exceptions → 500.

        Internal details are logged but NOT exposed in the response.
        """
        logger.exception("unhandled_error", exc_type=type(exc).__name__)
        body = {
            "data": None,
            "meta": {"request_id": getattr(request.state, "request_id", None)},
            "error": {
                "code": ErrorCode.INTERNAL_ERROR.value,
                "message": "An internal error occurred",
            },
        }
        return JSONResponse(status_code=500, content=body)
