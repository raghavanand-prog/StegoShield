"""Secure temporary-file handling for uploaded and generated images.

Design goals:
- Never trust a client-supplied filename for a filesystem path (path
  traversal prevention) - we always generate our own random name.
- Temporary files live under a single dedicated directory
  (Config.UPLOAD_TEMP_DIR) and are removed as soon as processing
  finishes, via a context manager so cleanup happens even on error.
- File permissions are restricted (0600) since uploaded content is
  untrusted.
- No uploaded bytes are ever passed to a shell command or `exec`.
"""
from __future__ import annotations

import contextlib
import os
import secrets
import uuid
from pathlib import Path

from app.config import Config
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


def ensure_temp_dir() -> Path:
    Config.UPLOAD_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    return Config.UPLOAD_TEMP_DIR


def generate_secure_filename(extension: str) -> str:
    """Generate a random, collision-resistant filename - never derived
    from user input, which eliminates path-traversal and filename-
    injection risk entirely (there is nothing user-controlled to inject).
    """
    ext = extension.lstrip(".").lower()
    token = f"{uuid.uuid4().hex}{secrets.token_hex(4)}"
    return f"{token}.{ext}"


@contextlib.contextmanager
def temporary_file(extension: str):
    """Context manager yielding a Path to a secure, empty temp file.

    The file (and nothing else in the directory) is removed on exit,
    whether the block succeeds or raises.
    """
    temp_dir = ensure_temp_dir()
    path = temp_dir / generate_secure_filename(extension)
    try:
        path.touch(mode=0o600, exist_ok=False)
        yield path
    finally:
        try:
            if path.exists():
                os.remove(path)
        except OSError as exc:  # pragma: no cover - best-effort cleanup
            logger.warning("temp_file_cleanup_failed", extra={"error": str(exc)})


def write_bytes_securely(path: Path, data: bytes) -> None:
    fd = os.open(str(path), os.O_WRONLY | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
    finally:
        pass
