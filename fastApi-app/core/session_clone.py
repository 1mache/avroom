from __future__ import annotations

"""Clone one room (session) into a new uid in the same project.

Inverse of :func:`core.session_teardown.delete_session_and_files` for the
artifacts that make a room look the same when reopened: Origin Photo,
Background, Preview, visible objects (cutouts + GLBs). Undo history, jobs,
mask candidates, and depth/normal/camera caches are intentionally skipped.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from core.image_processing import get_image_path
from core.inference_pool.session_runtime import acquire_canvas_writer, release_canvas_writer
from core.object_metadata import (
    ObjectMetadata,
    format_clone_name,
    list_object_ids,
    load_object_metadata,
    save_object_metadata,
)
from core.object_storage import (
    copy_file_preserving_mtime,
    current_background_path,
    object_cutout_path,
    object_glb_path,
    object_rotated_path,
    resolve_object_cutout_path,
    resolve_object_glb_path,
    session_preview_path,
)
from core.repositories.session_repo import (
    SessionNotFoundError,
    register_uid,
    set_session_name,
    touch_session,
)
from core.session_teardown import delete_session_and_files
from db.models import SessionRow
from db.session import session_scope
from settings import get_3d_storage_dir, get_image_storage_dir

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClonedSession:
    """Result of a successful room clone."""

    uid: str
    name: str
    last_changed: str


@dataclass(frozen=True)
class _SourceSession:
    """Fields needed from the source room before the DB session closes."""

    uid: str
    user_id: str
    project_id: str
    name: str | None


def _project_name_taken(project_id: str, name: str) -> bool:
    with session_scope() as db:
        existing = db.execute(
            select(SessionRow.id).where(
                SessionRow.project_id == project_id,
                SessionRow.name == name,
            )
        ).scalar_one_or_none()
        return existing is not None


def allocate_copy_room_name(project_id: str, source_name: str | None) -> str:
    """Return the next free ``{base}-copy`` / ``{base}-copyN`` name in *project_id*.

    Matches object-copy naming (:func:`format_clone_name`). Unnamed rooms
    use ``Untitled room`` as the base.
    """
    base = (source_name or "").strip() or "Untitled room"
    index = 0
    while True:
        candidate = format_clone_name(base, index)
        if not _project_name_taken(project_id, candidate):
            return candidate
        index += 1


def _load_source_session(uid: str) -> _SourceSession:
    """Return ownership/name fields for *uid*.

    Raises:
        SessionNotFoundError: When *uid* is unregistered.
    """
    with session_scope() as db:
        row = db.get(SessionRow, uid)
        if row is None:
            raise SessionNotFoundError(uid)
        return _SourceSession(
            uid=row.id,
            user_id=row.user_id,
            project_id=row.project_id,
            name=row.name,
        )


def _copy_session_files(source_uid: str, dest_uid: str) -> None:
    """Copy Origin Photo, Background, and Preview under *dest_uid*."""
    storage_dir = get_image_storage_dir()

    origin = get_image_path(source_uid, storage_dir)
    dest_origin = storage_dir / f"{dest_uid}{origin.suffix}"
    copy_file_preserving_mtime(origin, dest_origin)
    logger.debug("Cloned origin: %s -> %s", origin, dest_origin)

    background = current_background_path(storage_dir, source_uid)
    if background.exists():
        copy_file_preserving_mtime(
            background, current_background_path(storage_dir, dest_uid)
        )

    preview = session_preview_path(storage_dir, source_uid)
    if preview.exists():
        copy_file_preserving_mtime(preview, session_preview_path(storage_dir, dest_uid))


def _copy_object_files(source_uid: str, dest_uid: str, object_id: int) -> None:
    """Copy one object's cutout (required), optional GLB, and optional rotated PNG."""
    storage_dir = get_image_storage_dir()
    glb_dir = get_3d_storage_dir()

    source_cutout = resolve_object_cutout_path(storage_dir, source_uid, object_id)
    if not source_cutout.exists():
        raise FileNotFoundError(
            f"Source cutout not found for uid='{source_uid}' object_id={object_id}"
        )
    copy_file_preserving_mtime(
        source_cutout, object_cutout_path(storage_dir, dest_uid, object_id)
    )

    source_glb = resolve_object_glb_path(glb_dir, source_uid, object_id)
    if source_glb.exists():
        copy_file_preserving_mtime(
            source_glb, object_glb_path(glb_dir, dest_uid, object_id)
        )

    source_rotated = object_rotated_path(storage_dir, source_uid, object_id)
    if source_rotated.exists():
        copy_file_preserving_mtime(
            source_rotated, object_rotated_path(storage_dir, dest_uid, object_id)
        )


def _clone_visible_objects(source_uid: str, dest_uid: str) -> int:
    """Clone every currently-visible object into *dest_uid*. Returns count."""
    object_ids = list_object_ids(source_uid, visible_only=True)
    sources: list[ObjectMetadata] = []
    for oid in object_ids:
        meta = load_object_metadata(source_uid, oid)
        if meta is None:
            raise FileNotFoundError(
                f"Object metadata missing for uid='{source_uid}' object_id={oid}"
            )
        sources.append(meta)

    uuid_map = {meta.uuid: str(uuid.uuid4()) for meta in sources}
    now = datetime.now(UTC).isoformat()

    for meta in sources:
        remapped_root = (
            uuid_map.get(meta.clone_root_uuid, meta.clone_root_uuid)
            if meta.clone_root_uuid is not None
            else None
        )
        _copy_object_files(source_uid, dest_uid, meta.object_id)
        save_object_metadata(
            ObjectMetadata(
                uuid=uuid_map[meta.uuid],
                session_id=dest_uid,
                object_id=meta.object_id,
                name=meta.name,
                average_depth=meta.average_depth,
                source_elevation_deg=meta.source_elevation_deg,
                content_hash=meta.content_hash,
                created_at=now,
                clone_root_uuid=remapped_root,
                clone_root_label=meta.clone_root_label,
                clone_index=meta.clone_index,
                offset_x=meta.offset_x,
                offset_y=meta.offset_y,
                display_scale=meta.display_scale,
                stage_seq=0,
                is_3d=meta.is_3d,
                css_rotate_x_deg=meta.css_rotate_x_deg,
                css_rotate_y_deg=meta.css_rotate_y_deg,
                css_rotate_z_deg=meta.css_rotate_z_deg,
                css_perspective_px=meta.css_perspective_px,
                rotation_azimuth_deg=meta.rotation_azimuth_deg,
                rotation_relative_elevation_deg=meta.rotation_relative_elevation_deg,
                rotation_roll_deg=meta.rotation_roll_deg,
            )
        )

    return len(sources)


def clone_session(source_uid: str) -> ClonedSession:
    """Clone *source_uid* into a new room in the same project.

    Acquires the source session's canvas-writer lock so an in-flight inpaint
    cannot tear files mid-copy. On any failure after the new uid is
    registered, rolls back via :func:`delete_session_and_files`.

    Raises:
        SessionNotFoundError: When *source_uid* is unregistered.
        SessionConflictError: When the canvas writer cannot be acquired.
        FileNotFoundError: When the Origin Photo or a required cutout is missing.
    """
    source = _load_source_session(source_uid)
    new_name = allocate_copy_room_name(source.project_id, source.name)
    new_uid = str(uuid.uuid4())

    logger.info(
        "Cloning session: source_uid=%s dest_uid=%s name=%r",
        source_uid,
        new_uid,
        new_name,
    )

    acquire_canvas_writer(source_uid)
    registered = False
    try:
        register_uid(new_uid, user_id=source.user_id, project_id=source.project_id)
        registered = True
        set_session_name(new_uid, new_name)
        _copy_session_files(source_uid, new_uid)
        object_count = _clone_visible_objects(source_uid, new_uid)
        last_changed = touch_session(new_uid)
    except Exception:
        if registered:
            try:
                delete_session_and_files(new_uid)
            except Exception:
                logger.exception(
                    "Clone rollback failed: dest_uid=%s (leftover files may remain)",
                    new_uid,
                )
        raise
    finally:
        release_canvas_writer(source_uid)

    logger.info(
        "Session cloned: source_uid=%s dest_uid=%s name=%r objects=%d",
        source_uid,
        new_uid,
        new_name,
        object_count,
    )
    return ClonedSession(uid=new_uid, name=new_name, last_changed=last_changed)
