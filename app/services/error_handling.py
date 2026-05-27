"""Error taxonomy and structured error response model."""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel


# ── Exception taxonomy ────────────────────────────────────────────────────────


class EDMSBaseError(Exception):
    """Base class for all EDMS application errors."""

    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str = "An internal error occurred"):
        self.message = message
        super().__init__(message)


class ValidationError(EDMSBaseError):
    error_code: str = "VALIDATION_ERROR"

    def __init__(self, message: str = "Validation failed"):
        super().__init__(message)


class AuthenticationError(EDMSBaseError):
    error_code: str = "AUTHENTICATION_ERROR"

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message)


class PermissionError(EDMSBaseError):
    error_code: str = "PERMISSION_ERROR"

    def __init__(self, message: str = "Permission denied"):
        super().__init__(message)


class NotFoundError(EDMSBaseError):
    error_code: str = "NOT_FOUND"

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message)


class ConflictError(EDMSBaseError):
    error_code: str = "CONFLICT"

    def __init__(self, message: str = "Resource conflict"):
        super().__init__(message)


class ProcessingError(EDMSBaseError):
    error_code: str = "PROCESSING_ERROR"

    def __init__(self, message: str = "Processing failed"):
        super().__init__(message)


class StorageError(EDMSBaseError):
    error_code: str = "STORAGE_ERROR"

    def __init__(self, message: str = "Storage operation failed"):
        super().__init__(message)


class EncryptionError(EDMSBaseError):
    error_code: str = "ENCRYPTION_ERROR"

    def __init__(self, message: str = "Encryption operation failed"):
        super().__init__(message)


class KMSError(EDMSBaseError):
    error_code: str = "KMS_ERROR"

    def __init__(self, message: str = "KMS operation failed"):
        super().__init__(message)


# ── Structured error response model ──────────────────────────────────────────


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    detail: Optional[str] = None
    request_id: Optional[str] = None
    timestamp: datetime

    @classmethod
    def from_exception(
        cls, exc: EDMSBaseError, request_id: Optional[str] = None
    ) -> "ErrorResponse":
        return cls(
            error_code=exc.error_code,
            message=exc.message,
            request_id=request_id,
            timestamp=datetime.now(timezone.utc),
        )
