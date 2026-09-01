"""Central mapping from internal exceptions to safe, user-facing API errors.

Ensures no stack trace, file path, or internal exception message ever
reaches the client - callers get a stable error `code` plus a short,
actionable `message` while full details go to the server log only.
"""
from __future__ import annotations

from app.steganography.exceptions import (
    CapacityExceededError,
    EmptyMessageError,
    IntegrityVerificationError,
    InvalidImageError,
    NoHiddenDataError,
    SteganographyError,
)


class APIError(Exception):
    """Raised by route handlers to produce a structured JSON error response."""

    def __init__(self, message: str, status_code: int = 400, code: str = "bad_request"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message}}


def map_exception_to_api_error(exc: Exception) -> APIError:
    if isinstance(exc, CapacityExceededError):
        return APIError(str(exc), 422, "capacity_exceeded")
    if isinstance(exc, EmptyMessageError):
        return APIError(str(exc), 422, "empty_message")
    if isinstance(exc, NoHiddenDataError):
        return APIError(str(exc), 404, "no_hidden_data")
    if isinstance(exc, IntegrityVerificationError):
        return APIError(str(exc), 422, "integrity_failed")
    if isinstance(exc, InvalidImageError):
        return APIError(str(exc), 400, "invalid_image")
    if isinstance(exc, SteganographyError):
        return APIError(str(exc), 400, "steganography_error")
    return APIError("An unexpected error occurred while processing your request.", 500, "internal_error")
