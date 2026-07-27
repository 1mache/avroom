from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from core.inference_pool.session_runtime import acquire_canvas_writer, release_canvas_writer

_locks_guard = threading.Lock()
_session_locks: dict[str, threading.Lock] = {}


@contextmanager
def session_lock(session_id: str) -> Iterator[None]:
    """Serialize work for one session uid using the canvas writer lock.

    Prefer the explicit admit/acquire/release helpers in ``session_runtime`` for
    inpaint. This context manager remains for tests and legacy call sites that
    only need exclusive canvas access.
    """

    acquire_canvas_writer(session_id, timeout_sec=600)
    try:
        yield
    finally:
        release_canvas_writer(session_id)


@contextmanager
def legacy_session_lock(session_id: str) -> Iterator[None]:
    """Deprecated alias kept for older tests that expect a threading.Lock directly."""

    with _locks_guard:
        lock = _session_locks.setdefault(session_id, threading.Lock())
    with lock:
        yield
