from __future__ import annotations

"""Filesystem-backed metadata for finalized session objects.

Each processed object receives a UUID at inpaint time alongside the existing
sequential ``object_id``.  Metadata is stored per object as JSON and indexed
globally by UUID for O(1) lookup.
"""

import json
import logging
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, Field

from core.object_storage import list_object_ids, object_meta_path
from schemas.image import CutoutBounds, DEFAULT_SOURCE_ELEVATION_DEG
from settings import get_image_storage_dir

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


class ObjectIndexEntry(BaseModel):
    """Lightweight pointer from UUID to session-local object id."""

    session_id: str
    object_id: int


def get_object_index_file() -> Path:
    """Return path to the global UUID index (sibling of sessions.json)."""
    return get_image_storage_dir().parent / "object_index.json"


def _load_object_index() -> dict[str, ObjectIndexEntry]:
    index_path = get_object_index_file()
    if not index_path.exists():
        return {}
    try:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}
        return {
            str(key): ObjectIndexEntry.model_validate(value)
            for key, value in raw.items()
        }
    except (json.JSONDecodeError, ValueError):
        logger.warning("Malformed object index at %s — treating as empty", index_path)
        return {}


def _save_object_index(index: dict[str, ObjectIndexEntry]) -> None:
    index_path = get_object_index_file()
    index_path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {key: entry.model_dump() for key, entry in index.items()}
    index_path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")


def save_object_metadata(base_dir: Path, metadata: ObjectMetadata) -> None:
    """Persist object metadata JSON and register the UUID in the global index."""
    path = object_meta_path(base_dir, metadata.session_id, metadata.object_id)
    path.write_text(metadata.model_dump_json(indent=2), encoding="utf-8")

    index = _load_object_index()
    index[metadata.uuid] = ObjectIndexEntry(
        session_id=metadata.session_id,
        object_id=metadata.object_id,
    )
    _save_object_index(index)
    logger.info(
        "Saved object metadata: uuid=%s session_id=%s object_id=%d average_depth=%.2f source_elevation=%.2f",
        metadata.uuid,
        metadata.session_id,
        metadata.object_id,
        metadata.average_depth,
        metadata.source_elevation_deg,
    )


def load_object_metadata(base_dir: Path, session_id: str, object_id: int) -> ObjectMetadata | None:
    """Load metadata for one session object, or ``None`` if absent."""
    path = object_meta_path(base_dir, session_id, object_id)
    if not path.exists():
        return None
    try:
        return ObjectMetadata.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError:
        logger.warning("Malformed metadata file: %s", path)
        return None


def get_object_by_uuid(base_dir: Path, object_uuid: str) -> ObjectMetadata | None:
    """Resolve metadata by UUID using the global index."""
    index = _load_object_index()
    entry = index.get(object_uuid)
    if entry is None:
        return None
    return load_object_metadata(base_dir, entry.session_id, entry.object_id)


def _update_object_fields(
    base_dir: Path,
    object_uuid: str,
    updates: dict[str, Any],
) -> ObjectMetadata:
    """Rewrite one object's metadata JSON with *updates* applied.

    The UUID index is left alone on purpose: only ``session_id`` /
    ``object_id`` are indexed and neither is updatable here.

    Raises:
        FileNotFoundError: When no metadata record exists for *object_uuid*.
    """
    metadata = get_object_by_uuid(base_dir, object_uuid)
    if metadata is None:
        raise FileNotFoundError(f"Object metadata not found for uuid='{object_uuid}'")

    updated = metadata.model_copy(update=updates)
    path = object_meta_path(base_dir, updated.session_id, updated.object_id)
    path.write_text(updated.model_dump_json(indent=2), encoding="utf-8")
    return updated


def set_object_name(base_dir: Path, object_uuid: str, name: str | None) -> ObjectMetadata:
    """Update the optional name on an existing object metadata record."""
    updated = _update_object_fields(base_dir, object_uuid, {"name": name})
    logger.info("Updated object name: uuid=%s name=%r", object_uuid, name)
    return updated


def set_object_offset(base_dir: Path, object_uuid: str, offset_x: float, offset_y: float) -> ObjectMetadata:
    """Update the persisted drag offset on an existing object metadata record."""
    updated = _update_object_fields(
        base_dir,
        object_uuid,
        {"offset_x": offset_x, "offset_y": offset_y},
    )
    logger.info(
        "Updated object offset: uuid=%s offset_x=%.2f offset_y=%.2f",
        object_uuid,
        offset_x,
        offset_y,
    )
    return updated


def set_object_average_depth(base_dir: Path, object_uuid: str, average_depth: float) -> ObjectMetadata:
    """Update ``average_depth`` after a depth-based rescale placement."""
    updated = _update_object_fields(base_dir, object_uuid, {"average_depth": average_depth})
    logger.info(
        "Updated object average_depth: uuid=%s average_depth=%.2f",
        object_uuid,
        average_depth,
    )
    return updated


def set_object_rescale_state(
    base_dir: Path,
    object_uuid: str,
    *,
    average_depth: float,
    display_scale: float,
) -> ObjectMetadata:
    """Persist depth and cumulative UI scale after a smart-paste / rescale call."""
    updated = _update_object_fields(
        base_dir,
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


def delete_session_metadata(base_dir: Path, session_id: str, object_ids: list[int]) -> int:
    """Remove metadata JSON files and prune UUID index entries for a session."""
    index = _load_object_index()
    removed = 0
    uuids_to_remove: list[str] = []

    for object_id in object_ids:
        meta = load_object_metadata(base_dir, session_id, object_id)
        if meta is not None:
            uuids_to_remove.append(meta.uuid)

        path = object_meta_path(base_dir, session_id, object_id)
        if path.exists():
            path.unlink()
            removed += 1

    for object_uuid in uuids_to_remove:
        index.pop(object_uuid, None)

    if uuids_to_remove:
        _save_object_index(index)

    logger.debug(
        "Deleted session metadata: session_id=%s files_removed=%d index_pruned=%d",
        session_id,
        removed,
        len(uuids_to_remove),
    )
    return removed


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
    """Build a new metadata record with a fresh UUID and timestamp."""
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


def _iter_clones_of_root(base_dir: Path, session_id: str, root_uuid: str) -> Iterator[ObjectMetadata]:
    """Yield metadata for every finalized object in the session cloned from *root_uuid*."""

    for object_id in list_object_ids(base_dir, session_id):
        meta = load_object_metadata(base_dir, session_id, object_id)
        if meta is not None and meta.clone_root_uuid == root_uuid:
            yield meta


def _existing_clone_label(
    base_dir: Path,
    session_id: str,
    root_uuid: str,
) -> str | None:
    """Return the clone_root_label already used by clones of *root_uuid*, if any."""

    for meta in _iter_clones_of_root(base_dir, session_id, root_uuid):
        if meta.clone_root_label is not None:
            return meta.clone_root_label
    return None


def count_clones_of_root(base_dir: Path, session_id: str, root_uuid: str) -> int:
    """Return how many finalized objects in the session are clones of *root_uuid*."""

    return sum(1 for _ in _iter_clones_of_root(base_dir, session_id, root_uuid))


def resolve_clone_lineage(
    base_dir: Path,
    source: ObjectMetadata,
) -> tuple[str, str, int]:
    """Resolve ``(root_uuid, root_label, next_clone_index)`` for cloning *source*.

    Lineage is sticky: cloning a clone keeps the original root UUID/label so
    renamed copies and recursive duplicates do not reset the ordinal sequence.
    """

    if source.clone_root_uuid is not None and source.clone_root_label is not None:
        root_uuid = source.clone_root_uuid
        root_label = source.clone_root_label
    else:
        root_uuid = source.uuid
        existing_label = _existing_clone_label(base_dir, source.session_id, root_uuid)
        root_label = existing_label or default_object_label(source.object_id, source.name)

    next_index = count_clones_of_root(base_dir, source.session_id, root_uuid)
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
    base_dir: Path,
    source: ObjectMetadata,
    new_object_id: int,
    source_bounds: CutoutBounds | None = None,
) -> ObjectMetadata:
    """Build metadata for a clone of *source* with a fresh UUID and nickname.

    *source_bounds* (the source cutout's alpha bounds, if the caller already
    decoded it) drives a small leftward nudge on the clone's position so it
    doesn't land exactly on top of the source -- see _nudge_clone_offset.
    """

    root_uuid, root_label, clone_index = resolve_clone_lineage(base_dir, source)
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


def remove_object_index_entry(object_uuid: str) -> None:
    """Remove one UUID from the global object index if present."""

    index = _load_object_index()
    if object_uuid not in index:
        return
    index.pop(object_uuid, None)
    _save_object_index(index)
    logger.debug("Removed object index entry: uuid=%s", object_uuid)
