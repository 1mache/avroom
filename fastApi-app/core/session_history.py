from __future__ import annotations

"""Background canvas history: snapshot before overwrite, undo/redo, branch dump.

Each session keeps up to :data:`BACKGROUND_HISTORY_LIMIT` prior background
stages on disk as ``{uid}_bg_hist_{seq}.png``. The live canvas remains
``{uid}_background.png`` so existing read paths stay unchanged. Objects are
tagged with ``stage_seq`` at creation; only objects with ``stage_seq <= cursor``
are visible until the user redoes or a branch dump deletes them.
"""

import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select

from core.object_storage import (
    background_history_path,
    current_background_path,
    delete_legacy_object_artifacts,
    delete_object_artifact_files,
    remove_file,
)
from core.repositories.session_repo import SessionNotFoundError
from db.models import JobRow, ObjectRow, SessionRow
from db.session import session_scope
from settings import get_3d_storage_dir

logger = logging.getLogger(__name__)

BACKGROUND_HISTORY_LIMIT = 4


class HistoryConflictError(Exception):
    """Raised when undo/redo cannot run because canvas work is in flight."""


class HistoryBoundaryError(Exception):
    """Raised when undo/redo is requested past the available stack edge."""


@dataclass(frozen=True)
class HistoryFlags:
    """Whether backtrack/forward are available for one session."""

    can_undo: bool
    can_redo: bool
    history_cursor: int


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    try:
        tmp_path.write_bytes(data)
        os.replace(tmp_path, path)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise


def _atomic_copy_file(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = destination.with_suffix(f"{destination.suffix}.tmp")
    try:
        shutil.copy2(source, tmp_path)
        os.replace(tmp_path, destination)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise


def _get_session_row(session_id: str) -> SessionRow:
    with session_scope() as db:
        row = db.get(SessionRow, session_id)
        if row is None:
            raise SessionNotFoundError(f"Session not found for uid='{session_id}'")
        return row


def get_history_flags(session_id: str) -> HistoryFlags:
    """Return undo/redo availability for *session_id*."""

    row = _get_session_row(session_id)
    return HistoryFlags(
        can_undo=row.history_cursor > row.history_min,
        can_redo=row.history_cursor < row.history_head,
        history_cursor=row.history_cursor,
    )


def get_history_cursor(session_id: str) -> int:
    """Return the current history cursor for stamping duplicate/import objects."""

    return _get_session_row(session_id).history_cursor


def session_has_active_canvas_jobs(session_id: str) -> bool:
    """True when segment/inpaint/erase work is queued or running for *session_id*."""

    with session_scope() as db:
        count = db.execute(
            select(func.count())
            .select_from(JobRow)
            .where(
                JobRow.session_id == session_id,
                JobRow.kind.in_(("segment", "inpaint", "erase")),
                JobRow.status.in_(("queued", "running")),
            )
        ).scalar_one()
        return int(count) > 0


def _dump_forward_stages(
    db: object,
    *,
    session_id: str,
    cursor: int,
    head: int,
    base_dir: Path,
) -> None:
    """Delete redo stages and objects created after *cursor*."""

    if cursor >= head:
        return

    three_d_dir = get_3d_storage_dir()
    rows = db.execute(
        select(ObjectRow).where(ObjectRow.session_id == session_id, ObjectRow.stage_seq > cursor)
    ).scalars().all()
    for row in rows:
        delete_object_artifact_files(
            base_dir=base_dir,
            glb_dir=three_d_dir,
            uid=session_id,
            object_id=row.object_id,
        )
        if row.object_id == 0:
            delete_legacy_object_artifacts(base_dir=base_dir, glb_dir=three_d_dir, uid=session_id)
        db.delete(row)
        logger.info(
            "History branch dump removed object: session_id=%s object_id=%d stage_seq=%d",
            session_id,
            row.object_id,
            row.stage_seq,
        )

    for seq in range(cursor + 1, head + 1):
        removed = remove_file(background_history_path(base_dir, session_id, seq))
        if removed:
            logger.debug(
                "History branch dump removed snapshot: session_id=%s seq=%d",
                session_id,
                seq,
            )


def _evict_oldest_snapshot(session_id: str, history_min: int, base_dir: Path) -> int:
    removed = remove_file(background_history_path(base_dir, session_id, history_min))
    if removed:
        logger.debug(
            "History evicted oldest snapshot: session_id=%s seq=%d",
            session_id,
            history_min,
        )
    return history_min + 1


def _restore_live_from_cursor(session_id: str, cursor: int, base_dir: Path) -> None:
    live_path = current_background_path(base_dir, session_id)
    snapshot_path = background_history_path(base_dir, session_id, cursor)
    if snapshot_path.exists():
        _atomic_copy_file(snapshot_path, live_path)
        logger.debug(
            "Restored live background from snapshot: session_id=%s seq=%d",
            session_id,
            cursor,
        )
        return
    remove_file(live_path)
    logger.debug(
        "Restored live background to original upload: session_id=%s cursor=%d",
        session_id,
        cursor,
    )


def commit_background(session_id: str, background_bytes: bytes, base_dir: Path) -> int:
    """Snapshot the current canvas, write *background_bytes*, advance the stack.

    Returns the new ``history_cursor`` (use as ``stage_seq`` for a new object).

    Must run under the canvas-writer lock.
    """

    with session_scope() as db:
        row = db.get(SessionRow, session_id)
        if row is None:
            raise SessionNotFoundError(f"Session not found for uid='{session_id}'")

        if row.history_cursor < row.history_head:
            _dump_forward_stages(
                db,
                session_id=session_id,
                cursor=row.history_cursor,
                head=row.history_head,
                base_dir=base_dir,
            )
            row.history_head = row.history_cursor

        while row.history_cursor - row.history_min >= BACKGROUND_HISTORY_LIMIT:
            row.history_min = _evict_oldest_snapshot(session_id, row.history_min, base_dir)

        live_path = current_background_path(base_dir, session_id)
        if live_path.exists():
            _atomic_copy_file(
                live_path,
                background_history_path(base_dir, session_id, row.history_cursor),
            )

        _atomic_write_bytes(live_path, background_bytes)
        row.history_cursor += 1
        row.history_head = row.history_cursor
        new_cursor = row.history_cursor
        history_min = row.history_min
        history_head = row.history_head

    logger.info(
        "Background committed: session_id=%s cursor=%d min=%d head=%d bytes=%d",
        session_id,
        new_cursor,
        history_min,
        history_head,
        len(background_bytes),
    )
    return new_cursor


def undo_background(session_id: str, base_dir: Path) -> None:
    """Move one stage back. Must run under the canvas-writer lock."""

    if session_has_active_canvas_jobs(session_id):
        raise HistoryConflictError("Cannot backtrack while segment, inpaint, or erase work is in flight.")

    with session_scope() as db:
        row = db.get(SessionRow, session_id)
        if row is None:
            raise SessionNotFoundError(f"Session not found for uid='{session_id}'")
        if row.history_cursor <= row.history_min:
            raise HistoryBoundaryError("Nothing to backtrack to.")

        live_path = current_background_path(base_dir, session_id)
        if live_path.exists():
            _atomic_copy_file(
                live_path,
                background_history_path(base_dir, session_id, row.history_cursor),
            )

        row.history_cursor -= 1
        cursor = row.history_cursor

    _restore_live_from_cursor(session_id, cursor, base_dir)
    logger.info("Background undo: session_id=%s cursor=%d", session_id, cursor)


def redo_background(session_id: str, base_dir: Path) -> None:
    """Move one stage forward. Must run under the canvas-writer lock."""

    if session_has_active_canvas_jobs(session_id):
        raise HistoryConflictError("Cannot move forward while segment, inpaint, or erase work is in flight.")

    with session_scope() as db:
        row = db.get(SessionRow, session_id)
        if row is None:
            raise SessionNotFoundError(f"Session not found for uid='{session_id}'")
        if row.history_cursor >= row.history_head:
            raise HistoryBoundaryError("Nothing to move forward to.")

        live_path = current_background_path(base_dir, session_id)
        if live_path.exists():
            _atomic_copy_file(
                live_path,
                background_history_path(base_dir, session_id, row.history_cursor),
            )

        row.history_cursor += 1
        cursor = row.history_cursor

    _restore_live_from_cursor(session_id, cursor, base_dir)
    logger.info("Background redo: session_id=%s cursor=%d", session_id, cursor)
