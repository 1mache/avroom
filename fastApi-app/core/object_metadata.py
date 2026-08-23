from __future__ import annotations

"""Postgres-backed metadata for finalized session objects.

Each processed object receives a UUID at inpaint time alongside the existing
sequential ``object_id``. Metadata (and the UUID -> (session, object) index)
now lives in the `objects` table (`db/models.py::ObjectRow`) instead of a
per-object JSON file plus a separate global index file.
"""

import logging
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from db.models import ObjectRow
from db.session import session_scope
from schemas.image import CutoutBounds, DEFAULT_SOURCE_ELEVATION_DEG

logger = logging.getLogger(__name__)


class ObjectMetadata(BaseModel):
    """Persistent metadata for one finalized object within a session."""

    uuid: Annotated[
        str,
        Field(description="Server-generated UUID; primary searchable key."),
    ]
    session_id: Annotated[
        str,
        Field(description="Session UID (same as upload image_id)."),
    ]
    object_id: Annotated[
        int,
        Field(ge=0, description="Zero-based integer id within the session."),
    ]
    name: Annotated[
        str | None,
        Field(default=None, description="Optional human-readable label."),
    ]
    average_depth: Annotated[
        float,
        Field(description="Mean uint8 depth over the selected mask at creation."),
    ]
    source_elevation_deg: Annotated[
        float,
        Field(
            default=DEFAULT_SOURCE_ELEVATION_DEG,
            description="Estimated Zero123 source elevation for this object (degrees).",
        ),
    ]
    content_hash: Annotated[
        str,
        Field(description="SHA-256 hex of canvas bytes when the object was created."),
    ]
    created_at: Annotated[
        str,
        Field(description="ISO-8601 UTC timestamp of object creation."),
    ]
    clone_root_uuid: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "UUID of the original non-clone root this object was duplicated from. "
                "None for objects that are not clones."
            ),
        ),
    ]
    clone_root_label: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Stable display label of the clone root used for copy naming "
                "(e.g. 'Chair' or 'Object 0'). None for non-clones."
            ),
        ),
    ]
    clone_index: Annotated[
        int | None,
        Field(
            default=None,
            ge=0,
            description=(
                "Zero-based clone ordinal under clone_root_uuid. "
                "0 → '<label>-copy', 1 → '<label>-copy1', etc. None for non-clones."
            ),
        ),
    ]
    offset_x: Annotated[
        float,
        Field(default=0.0, description="Persisted drag offset X from center, natural-image pixels."),
    ]
    offset_y: Annotated[
        float,
        Field(default=0.0, description="Persisted drag offset Y from center, natural-image pixels."),
    ]
    display_scale: Annotated[
        float,
        Field(
            default=1.0,
            gt=0.0,
            description="Cumulative UI display scale; cutout PNG stays at original resolution.",
        ),
    ]


def _row_to_metadata(row: ObjectRow) -> ObjectMetadata:
    return ObjectMetadata(
        uuid=row.uuid,
        session_id=row.session_id,
        object_id=row.object_id,
        name=row.name,
        average_depth=row.average_depth,
        source_elevation_deg=row.source_elevation_deg,
        content_hash=row.content_hash,
        created_at=row.created_at.isoformat(),
        clone_root_uuid=row.clone_root_uuid,
        clone_root_label=row.clone_root_label,
        clone_index=row.clone_index,
        offset_x=row.offset_x,
        offset_y=row.offset_y,
        display_scale=row.display_scale,
    )


def save_object_metadata(metadata: ObjectMetadata) -> None:
    """Persist a new object metadata row.

    Ensures the owning session row exists first (auto-provisioning it under
    the local dev user if not) so this matches the old JSON-sidecar
    behavior, where object metadata and session registration were fully
    decoupled files.
    """
    from core.repositories.session_repo import register_uid

    register_uid(metadata.session_id)
    with session_scope() as db:
        db.add(
            ObjectRow(
                uuid=metadata.uuid,
                session_id=metadata.session_id,
                object_id=metadata.object_id,
                name=metadata.name,
                average_depth=metadata.average_depth,
                source_elevation_deg=metadata.source_elevation_deg,
                content_hash=metadata.content_hash,
                created_at=datetime.fromisoformat(metadata.created_at),
                clone_root_uuid=metadata.clone_root_uuid,
                clone_root_label=metadata.clone_root_label,
                clone_index=metadata.clone_index,
                offset_x=metadata.offset_x,
                offset_y=metadata.offset_y,
                display_scale=metadata.display_scale,
            )
        )
    logger.info(
        "Saved object metadata: uuid=%s session_id=%s object_id=%d average_depth=%.2f source_elevation=%.2f",
        metadata.uuid,
        metadata.session_id,
        metadata.object_id,
        metadata.average_depth,
        metadata.source_elevation_deg,
    )


def load_object_metadata(session_id: str, object_id: int) -> ObjectMetadata | None:
    """Load metadata for one session object, or ``None`` if absent."""
    with session_scope() as db:
        row = db.execute(
            select(ObjectRow).where(
                ObjectRow.session_id == session_id, ObjectRow.object_id == object_id
            )
        ).scalar_one_or_none()
        return _row_to_metadata(row) if row is not None else None


def get_object_by_uuid(object_uuid: str) -> ObjectMetadata | None:
    """Resolve metadata by UUID."""
    with session_scope() as db:
        row = db.get(ObjectRow, object_uuid)
        return _row_to_metadata(row) if row is not None else None


def list_object_ids(session_id: str) -> list[int]:
    """Return sorted list of object ids for *session_id*."""
    with session_scope() as db:
        rows = db.execute(
            select(ObjectRow.object_id)
            .where(ObjectRow.session_id == session_id)
            .order_by(ObjectRow.object_id)
        ).scalars().all()
        return list(rows)


def next_object_id(session_id: str) -> int:
    """Return the next available object id for *session_id* (``0`` if none exist).

    Relies on the canvas-writer lock (``core/inference_pool/session_runtime.py``)
    already serializing inpaint/duplicate per session on a single instance —
    see ``docs/backend/concurrency.md`` — rather than a row lock here.
    """
    with session_scope() as db:
        highest = db.execute(
            select(func.max(ObjectRow.object_id)).where(ObjectRow.session_id == session_id)
        ).scalar_one()
        return 0 if highest is None else highest + 1


def _update_object_fields(object_uuid: str, updates: dict[str, Any]) -> ObjectMetadata:
    """Apply *updates* to one object's row and return the resulting metadata.

    Raises:
        FileNotFoundError: When no metadata record exists for *object_uuid*
            (kept as `FileNotFoundError` for compatibility with existing
            callers that already catch it as "object not found").
    """
    with session_scope() as db:
        row = db.get(ObjectRow, object_uuid)
        if row is None:
            raise FileNotFoundError(f"Object metadata not found for uuid='{object_uuid}'")
        for key, value in updates.items():
            setattr(row, key, value)
        db.flush()
        return _row_to_metadata(row)


def set_object_name(object_uuid: str, name: str | None) -> ObjectMetadata:
    """Update the optional name on an existing object metadata record."""
    updated = _update_object_fields(object_uuid, {"name": name})
    logger.info("Updated object name: uuid=%s name=%r", object_uuid, name)
    return updated


def set_object_offset(object_uuid: str, offset_x: float, offset_y: float) -> ObjectMetadata:
    """Update the persisted drag offset on an existing object metadata record."""
    updated = _update_object_fields(object_uuid, {"offset_x": offset_x, "offset_y": offset_y})
    logger.info(
        "Updated object offset: uuid=%s offset_x=%.2f offset_y=%.2f",
        object_uuid,
        offset_x,
        offset_y,
    )
    return updated


def set_object_average_depth(object_uuid: str, average_depth: float) -> ObjectMetadata:
    """Update ``average_depth`` after a depth-based rescale placement."""
    updated = _update_object_fields(object_uuid, {"average_depth": average_depth})
    logger.info(
        "Updated object average_depth: uuid=%s average_depth=%.2f",
        object_uuid,
        average_depth,
    )
    return updated


def set_object_rescale_state(
    object_uuid: str,
    *,
    average_depth: float,
    display_scale: float,
) -> ObjectMetadata:
    """Persist depth and cumulative UI scale after a smart-paste / rescale call."""
    updated = _update_object_fields(
        object_uuid,
        {"average_depth": average_depth, "display_scale": display_scale},
    )
    logger.info(
        "Updated object rescale state: uuid=%s average_depth=%.2f display_scale=%.4f",
        object_uuid,
        average_depth,
        display_scale,
    )
    return updated


def delete_session_metadata(session_id: str, object_ids: list[int]) -> int:
    """Delete metadata rows for the given object ids within one session."""
    if not object_ids:
        return 0
    with session_scope() as db:
        rows = db.execute(
            select(ObjectRow).where(
                ObjectRow.session_id == session_id, ObjectRow.object_id.in_(object_ids)
            )
        ).scalars().all()
        removed = len(rows)
        for row in rows:
            db.delete(row)
    logger.debug("Deleted session metadata: session_id=%s rows_removed=%d", session_id, removed)
    return removed


def remove_object_index_entry(object_uuid: str) -> None:
    """Delete one object's metadata row by UUID. No-op if already absent."""
    with session_scope() as db:
        row = db.get(ObjectRow, object_uuid)
        if row is None:
            return
        db.delete(row)
    logger.debug("Removed object metadata row: uuid=%s", object_uuid)


def create_object_metadata(
    *,
    session_id: str,
    object_id: int,
    average_depth: float,
    content_hash: str,
    source_elevation_deg: float = DEFAULT_SOURCE_ELEVATION_DEG,
    name: str | None = None,
    clone_root_uuid: str | None = None,
    clone_root_label: str | None = None,
    clone_index: int | None = None,
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    display_scale: float = 1.0,
) -> ObjectMetadata:
    """Build a new metadata record with a fresh UUID and timestamp (not persisted)."""
    return ObjectMetadata(
        uuid=str(uuid.uuid4()),
        session_id=session_id,
        object_id=object_id,
        name=name,
        average_depth=average_depth,
        source_elevation_deg=source_elevation_deg,
        content_hash=content_hash,
        created_at=datetime.now(UTC).isoformat(),
        clone_root_uuid=clone_root_uuid,
        clone_root_label=clone_root_label,
        clone_index=clone_index,
        offset_x=offset_x,
        offset_y=offset_y,
        display_scale=display_scale,
    )


def default_object_label(object_id: int, name: str | None) -> str:
    """Return the display label used as a clone-name base for *object_id*."""

    if name is not None and name.strip():
        return name.strip()
    return f"Object {object_id}"


def format_clone_name(root_label: str, clone_index: int) -> str:
    """Format a clone nickname from a root label and zero-based ordinal.

    Index ``0`` yields ``"<label>-copy"``; subsequent indices append the
    ordinal (``"<label>-copy1"``, ``"<label>-copy2"``, …).
    """

    if clone_index < 0:
        raise ValueError(f"clone_index must be >= 0 (got {clone_index})")
    if clone_index == 0:
        return f"{root_label}-copy"
    return f"{root_label}-copy{clone_index}"


def _iter_clones_of_root(session_id: str, root_uuid: str) -> Iterator[ObjectMetadata]:
    """Yield metadata for every finalized object in the session cloned from *root_uuid*."""
    with session_scope() as db:
        rows = db.execute(
            select(ObjectRow).where(
                ObjectRow.session_id == session_id, ObjectRow.clone_root_uuid == root_uuid
            )
        ).scalars().all()
        for row in rows:
            yield _row_to_metadata(row)


def _existing_clone_label(session_id: str, root_uuid: str) -> str | None:
    """Return the clone_root_label already used by clones of *root_uuid*, if any."""

    for meta in _iter_clones_of_root(session_id, root_uuid):
        if meta.clone_root_label is not None:
            return meta.clone_root_label
    return None


def count_clones_of_root(session_id: str, root_uuid: str) -> int:
    """Return how many finalized objects in the session are clones of *root_uuid*."""
    with session_scope() as db:
        return db.execute(
            select(func.count()).where(
                ObjectRow.session_id == session_id, ObjectRow.clone_root_uuid == root_uuid
            )
        ).scalar_one()


def resolve_clone_lineage(source: ObjectMetadata) -> tuple[str, str, int]:
    """Resolve ``(root_uuid, root_label, next_clone_index)`` for cloning *source*.

    Lineage is sticky: cloning a clone keeps the original root UUID/label so
    renamed copies and recursive duplicates do not reset the ordinal sequence.
    """

    if source.clone_root_uuid is not None and source.clone_root_label is not None:
        root_uuid = source.clone_root_uuid
        root_label = source.clone_root_label
    else:
        root_uuid = source.uuid
        existing_label = _existing_clone_label(source.session_id, root_uuid)
        root_label = existing_label or default_object_label(source.object_id, source.name)

    next_index = count_clones_of_root(source.session_id, root_uuid)
    return root_uuid, root_label, next_index


def _nudge_clone_offset(source: ObjectMetadata, bounds: CutoutBounds | None) -> tuple[float, float]:
    """Nudge a clone's X offset left of the source by ~15% of its own width.

    Falls back to nudging right if there's no room on the left, and to the
    source's exact offset if there's no room on either side (or bounds
    couldn't be determined) -- a clone landing exactly on its source is a
    rare degenerate case, never worth failing the duplicate over. Vertical
    offset is always copied unchanged (horizontal nudge only).
    """
    if bounds is None:
        return source.offset_x, source.offset_y

    width = bounds.right - bounds.left
    nudge = max(12.0, width * 0.15)
    min_x = -bounds.left
    max_x = bounds.natural_width - bounds.right

    left_candidate = source.offset_x - nudge
    if left_candidate >= min_x:
        return left_candidate, source.offset_y

    right_candidate = source.offset_x + nudge
    if right_candidate <= max_x:
        return right_candidate, source.offset_y

    return source.offset_x, source.offset_y


def build_clone_metadata(
    source: ObjectMetadata,
    new_object_id: int,
    source_bounds: CutoutBounds | None = None,
) -> ObjectMetadata:
    """Build metadata for a clone of *source* with a fresh UUID and nickname.

    *source_bounds* (the source cutout's alpha bounds, if the caller already
    decoded it) drives a small leftward nudge on the clone's position so it
    doesn't land exactly on top of the source -- see _nudge_clone_offset.
    """

    root_uuid, root_label, clone_index = resolve_clone_lineage(source)
    clone_name = format_clone_name(root_label, clone_index)
    offset_x, offset_y = _nudge_clone_offset(source, source_bounds)
    return create_object_metadata(
        session_id=source.session_id,
        object_id=new_object_id,
        average_depth=source.average_depth,
        content_hash=source.content_hash,
        source_elevation_deg=source.source_elevation_deg,
        name=clone_name,
        clone_root_uuid=root_uuid,
        clone_root_label=root_label,
        clone_index=clone_index,
        offset_x=offset_x,
        offset_y=offset_y,
        display_scale=source.display_scale,
    )
