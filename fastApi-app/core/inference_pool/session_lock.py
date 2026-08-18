from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from core.inference_pool.session_runtime import acquire_canvas_writer, release_canvas_writer


@contextmanager
def session_lock(session_id: str) -> Iterator[None]:
    """Serialize work for one session uid using the canvas writer lock.

    Prefer the explicit admit/acquire/release helpers in ``session_runtime`` for
    inpaint. This context manager remains for tests and legacy call sites that
    only need exclusive canvas access. Wait timeout follows
    ``INFERENCE_JOB_TIMEOUT`` / ``INFERENCE_JOB_TIMEOUT_SEC``.
    """

    acquire_canvas_writer(session_id)
    try:
        yield
    finally:
        release_canvas_writer(session_id)
