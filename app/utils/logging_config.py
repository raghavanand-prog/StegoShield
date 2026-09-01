"""Structured application logging.

Logs operation name, success/failure, and processing time as
machine-parseable `extra` fields. Secret message contents and raw
uploaded image bytes are NEVER logged - only metadata (sizes, shapes,
timings, error categories).
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from app.config import Config

_CONFIGURED = False


class SafeFormatter(logging.Formatter):
    """Formatter that appends any `extra` fields as key=value pairs."""

    RESERVED = set(logging.LogRecord(None, None, "", 0, "", None, None).__dict__.keys())

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {
            k: v
            for k, v in record.__dict__.items()
            if k not in self.RESERVED and not k.startswith("_")
        }
        if extras:
            extra_str = " ".join(f"{k}={v}" for k, v in sorted(extras.items()))
            return f"{base} | {extra_str}"
        return base


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    root = logging.getLogger("stegoshield")
    root.setLevel(getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO))
    fmt = SafeFormatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    try:
        Config.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            Config.LOG_FILE, maxBytes=2_000_000, backupCount=3
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except OSError:  # pragma: no cover - read-only filesystem fallback
        root.warning("Could not open log file; logging to console only.")

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(f"stegoshield.{name}")
