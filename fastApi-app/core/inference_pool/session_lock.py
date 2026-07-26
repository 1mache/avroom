from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

_locks_guard = threading.Lock()
_session_locks: dict[str, threading.Lock] = {}


@contextmanager
def session_lock(session_id: str) -> Iterator[None]:
    """Serialize inpaint post-processing for one session uid.

    Prevents duplicate ``object_id`` allocation when concurrent inpaint requests
    target the same session while GPU work is serialized separately.
    """
    with _locks_guard:
        lock = _session_locks.setdefault(session_id, threading.Lock())
    with lock:
        yield
