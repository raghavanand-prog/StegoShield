"""Small in-memory recent-activity log powering the Dashboard's "Recent
Analysis" panel.

Deliberately not backed by a database (out of scope for this project's
stack) and intentionally non-persistent: it resets on every app
restart. Only operation metadata is stored - never secret message
content or raw image bytes.

Known limitation (documented, not silently ignored - see
docs/security-review.md): this deque is process-local state. Under a
multi-process deployment (e.g. `gunicorn ... --workers 2`, as this
project's own README suggests for production), each worker process has
its own independent copy, so a request handled by one worker will not
show up in "Recent Analysis" if the browser's next request lands on a
different worker. This is a single-instance-friendly UX convenience,
not a source of truth - it never gates any security decision, so the
inconsistency is a cosmetic dashboard quirk rather than a correctness
or security bug. A real multi-worker deployment wanting a consistent
activity feed would back this with shared storage (Redis, a database)
instead.
"""
from __future__ import annotations

import threading
import time
from collections import deque

_LOCK = threading.Lock()
_LOG: deque = deque(maxlen=25)


def record(operation: str, summary: dict) -> None:
    with _LOCK:
        _LOG.appendleft(
            {
                "operation": operation,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                **summary,
            }
        )


def recent(limit: int = 10) -> list[dict]:
    with _LOCK:
        return list(_LOG)[:limit]
