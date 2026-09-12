"""Small HTTP-facing helpers shared by every router under ``/images``.

Both helpers here existed as copy-pasted blocks in eight-plus route bodies
before: an object lookup that 404s, and the canvas-writer acquire/release
sandwich that 409s on timeout. They live in one module so the *wording* of a
404 detail and the *status* of a lock timeout are decided once, not per route.

Kept separate from ``core/`` on purpose: ``core`` must stay free of
``HTTPException`` so the job dispatcher and the archive importer can reuse the
same primitives without FastAPI in scope.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException

from core.inference_pool.session_runtime import (
    SessionConflictError,
    acquire_canvas_writer,
    release_canvas_writer,
)
from core.object_metadata import ObjectMetadata, get_object_by_uuid

logger = logging.getLogger(__name__)


def require_object(object_uuid: str) -> ObjectMetadata:
    """Return one object's metadata, or raise HTTP 404 if no such object exists.

    The detail string is deliberately identical for every caller — an object
    that is missing and an object that belongs to someone else must be
    indistinguishable from outside (see ``core.auth.ownership``).
    """
    metadata = get_object_by_uuid(object_uuid)
    if metadata is None:
        logger.warning("Object not found: uuid=%s", object_uuid)
        raise HTTPException(status_code=404, detail=f"Object not found for uuid='{object_uuid}'")
    return metadata


@contextmanager
def canvas_writer(session_id: str, *, action: str) -> Iterator[None]:
    """Hold a session's canvas-writer lock for the duration of an HTTP request.

    Only *acquisition* is translated: a wait timeout becomes HTTP 409, exactly
    as each of these routes did by hand. A ``SessionConflictError`` raised by
    the body itself is left alone, so it still reaches the generic error path
    rather than being silently relabelled as a lock conflict.

    Args:
        session_id: The session (room) uid whose canvas is being written.
        action: Human-readable operation name, used only in the warning log.
    """
    try:
        acquire_canvas_writer(session_id)
    except SessionConflictError as exc:
        logger.warning("%s rejected — canvas writer timeout: session_id=%s", action, session_id)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        yield
    finally:
        release_canvas_writer(session_id)
