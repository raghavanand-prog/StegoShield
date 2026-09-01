"""Domain-specific exceptions for the steganography engine.

Keeping these separate from generic Exceptions lets the API layer map
each one to a clean, user-facing error message instead of leaking a
stack trace (see app/routes and app/utils/errors.py).
"""


class SteganographyError(Exception):
    """Base class for all steganography-engine errors."""


class CapacityExceededError(SteganographyError):
    """Raised when the secret message will not fit inside the cover image."""

    def __init__(self, message_bytes: int, capacity_bytes: int):
        self.message_bytes = message_bytes
        self.capacity_bytes = capacity_bytes
        super().__init__(
            f"Message ({message_bytes} bytes) exceeds maximum capacity "
            f"({capacity_bytes} bytes) for this image."
        )


class EmptyMessageError(SteganographyError):
    """Raised when the caller attempts to encode an empty message."""


class InvalidImageError(SteganographyError):
    """Raised when an uploaded file is not a usable image."""


class NoHiddenDataError(SteganographyError):
    """Raised when a decode is attempted on an image with no valid payload."""


class IntegrityVerificationError(SteganographyError):
    """Raised when a payload's checksum does not match its content.

    This indicates the image was modified/re-compressed/corrupted after
    encoding, or the image never contained a StegoShield payload at the
    position expected.
    """
