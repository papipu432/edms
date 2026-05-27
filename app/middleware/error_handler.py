"""Request ID middleware and global exception handlers."""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.services.error_handling import (
    AuthenticationError,
    ConflictError,
    EDMSBaseError,
    EncryptionError,
    ErrorResponse,
    KMSError,
    NotFoundError,
    PermissionError,
    ProcessingError,
    StorageError,
    ValidationError,
)

logger = logging.getLogger(__name__)

# Mapping of exception classes to HTTP status codes
EXCEPTION_STATUS_MAP: dict[type, int] = {
    ValidationError: 400,
    AuthenticationError: 401,
    PermissionError: 403,
    NotFoundError: 404,
    ConflictError: 409,
    ProcessingError: 500,
    StorageError: 500,
    EncryptionError: 500,
    KMSError: 500,
}


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware that generates a UUID for each request and adds X-Request-ID header."""

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        try:
            response = await call_next(request)
        except EDMSBaseError as exc:
            status_code = EXCEPTION_STATUS_MAP.get(type(exc), 500)
            error_response = ErrorResponse.from_exception(exc, request_id=request_id)
            logger.error(
                "EDMS error [%s] request_id=%s: %s",
                exc.error_code,
                request_id,
                exc.message,
            )
            response = JSONResponse(
                status_code=status_code,
                content=error_response.model_dump(mode="json"),
            )
        except Exception as exc:
            logger.error(
                "Unhandled exception request_id=%s: %s: %s",
                request_id,
                type(exc).__name__,
                str(exc),
            )
            error_response = ErrorResponse(
                error_code="INTERNAL_ERROR",
                message="An internal server error occurred",
                request_id=request_id,
                timestamp=datetime.now(timezone.utc),
            )
            response = JSONResponse(
                status_code=500,
                content=error_response.model_dump(mode="json"),
            )

        response.headers["X-Request-ID"] = request_id
        return response


def _get_request_id(request: Request) -> str | None:
    """Safely extract request_id from request state."""
    return getattr(request.state, "request_id", None)


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI app."""

    @app.exception_handler(EDMSBaseError)
    async def edms_exception_handler(request: Request, exc: EDMSBaseError):
        request_id = _get_request_id(request)
        status_code = EXCEPTION_STATUS_MAP.get(type(exc), 500)

        error_response = ErrorResponse.from_exception(exc, request_id=request_id)

        logger.error(
            "EDMS error [%s] request_id=%s: %s",
            exc.error_code,
            request_id,
            exc.message,
        )

        return JSONResponse(
            status_code=status_code,
            content=error_response.model_dump(mode="json"),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        request_id = _get_request_id(request)

        logger.error(
            "Unhandled exception request_id=%s: %s: %s",
            request_id,
            type(exc).__name__,
            str(exc),
        )

        error_response = ErrorResponse(
            error_code="INTERNAL_ERROR",
            message="An internal server error occurred",
            request_id=request_id,
            timestamp=datetime.now(timezone.utc),
        )

        return JSONResponse(
            status_code=500,
            content=error_response.model_dump(mode="json"),
        )
