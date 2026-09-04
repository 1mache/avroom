from __future__ import annotations

"""Project export/import as a single self-contained zip.

Bundles every room in a project -- its DB metadata (name, history counters,
object rows) plus every blob it owns (original upload, canvas, undo
snapshots, cutouts, GLBs) -- so a project can move to a different machine
with fresh session/object/project ids minted on import.

The blob inventory here is the photographic negative of
`core.session_teardown.delete_session_and_files`: anything teardown deletes
is, by definition, something export should carry. Keep the two in sync.
Depth/normal caches (`{uid}_depth_*.npy` / `{uid}_normal_*.npy`) and
transient SAM candidates (`{uid}_mask_*`) are deliberately excluded --
recomputable, and a float32 normal map alone can dwarf every visible file in
a room combined.
"""

import json
import logging
import re
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.object_metadata import ObjectMetadata, list_object_ids, load_object_metadata, save_object_metadata
from core.repositories import project_repo, session_repo
from settings import get_3d_storage_dir, get_image_storage_dir

logger = logging.getLogger(__name__)

ARCHIVE_FORMAT = 1
MANIFEST_NAME = "manifest.json"

_IMAGES_DIR = "images"
_GLB_DIR = "3d"
_SKIP_SUBSTRINGS = ("_depth_", "_normal_", "_mask_")

# Matches exactly one path segment under images/ or 3d/ -- the zip-slip
# guard. Destination paths are built from a freshly minted uid plus this
# validated basename, never by joining an archive-supplied path directly.
_ENTRY_RE = re.compile(r"^(images|3d)/([^/\\]+)$")


class ArchiveFormatError(ValueError):
    """Raised when a zip has no manifest, a malformed one, or an unsupported format."""


def _room_blob_paths(storage_dir: Path, glb_dir: Path, uid: str) -> list[tuple[Path, str]]:
    """Return `(source_path, archive_name)` pairs for every blob one room owns.

    Two glob patterns per directory (never a single `f"{uid}*"`) so one uid
    can never sweep in another uid's files that merely share a prefix.
    """
    pairs: list[tuple[Path, str]] = []
    for pattern in (f"{uid}.*", f"{uid}_*"):
        for path in storage_dir.glob(pattern):
            if path.is_file() and path.suffix != ".tmp" and not any(s in path.name for s in _SKIP_SUBSTRINGS):
                pairs.append((path, f"{_IMAGES_DIR}/{path.name}"))
        for path in glb_dir.glob(pattern):
            if path.is_file() and path.suffix != ".tmp":
                pairs.append((path, f"{_GLB_DIR}/{path.name}"))
    return pairs


def build_project_archive(project_id: str, out_path: Path) -> None:
    """Write a project (every room, its metadata, and its blobs) to a zip at *out_path*.

    Raises:
        project_repo.ProjectNotFoundError: When *project_id* doesn't exist.
    """
    summary = project_repo.get_project(project_id)
    if summary is None:
        raise project_repo.ProjectNotFoundError(project_id)

    storage_dir = get_image_storage_dir()
    glb_dir = get_3d_storage_dir()
    room_ids = project_repo.list_project_session_ids(project_id)

    rooms_manifest: list[dict[str, Any]] = []
    file_count = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_STORED) as zf:
        for uid in room_ids:
            state = session_repo.get_session_state(uid)
            if state is None:  # pragma: no cover - defensive; FK guarantees this can't happen
                logger.warning("Project archive: room vanished mid-export, skipping: uid=%s", uid)
                continue

            objects: list[dict[str, Any]] = []
            for object_id in list_object_ids(uid):
                metadata = load_object_metadata(uid, object_id)
                if metadata is not None:
                    objects.append(metadata.model_dump())

            rooms_manifest.append(
                {
                    "uid": uid,
                    "name": state.name,
                    "created_at": state.created_at,
                    "last_changed": state.last_changed,
                    "history_min": state.history_min,
                    "history_cursor": state.history_cursor,
                    "history_head": state.history_head,
                    "objects": objects,
                }
            )
            for source_path, archive_name in _room_blob_paths(storage_dir, glb_dir, uid):
                zf.write(source_path, archive_name)
                file_count += 1

        manifest = {
            "format": ARCHIVE_FORMAT,
            "exported_at": datetime.now(UTC).isoformat(),
            "project": {"name": summary.name},
            "rooms": rooms_manifest,
        }
        zf.writestr(MANIFEST_NAME, json.dumps(manifest))

    logger.info(
        "Project archive built: project_id=%s rooms=%d files=%d out_path=%s",
        project_id,
        len(room_ids),
        file_count,
        out_path,
    )


def _read_manifest(zf: zipfile.ZipFile) -> dict[str, Any]:
    try:
        raw = zf.read(MANIFEST_NAME)
    except KeyError as exc:
        raise ArchiveFormatError("Zip has no manifest.json") from exc
    try:
        manifest: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ArchiveFormatError("manifest.json is not valid JSON") from exc
    if manifest.get("format") != ARCHIVE_FORMAT:
        raise ArchiveFormatError(f"Unsupported archive format: {manifest.get('format')!r}")
    return manifest


def _restore_room_files(
    zf: zipfile.ZipFile, *, old_uid: str, new_uid: str, storage_dir: Path, glb_dir: Path
) -> int:
    """Extract every zip entry belonging to *old_uid*, writing it back under *new_uid*."""
    written = 0
    for entry in zf.namelist():
        match = _ENTRY_RE.match(entry)
        if match is None:
            continue
        kind, basename = match.groups()
        if not (basename.startswith(f"{old_uid}.") or basename.startswith(f"{old_uid}_")):
            continue
        dest_dir = storage_dir if kind == _IMAGES_DIR else glb_dir
        dest_path = dest_dir / (new_uid + basename[len(old_uid) :])
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(zf.read(entry))
        written += 1
    return written


def _restore_room_objects(room: dict[str, Any], new_uid: str) -> int:
    """Persist every object in *room* under *new_uid*, with fresh uuids and remapped clone lineage."""
    uuid_map = {obj["uuid"]: str(uuid.uuid4()) for obj in room.get("objects", [])}
    for obj in room.get("objects", []):
        clone_root_uuid = obj.get("clone_root_uuid")
        fields = {
            **obj,
            "uuid": uuid_map[obj["uuid"]],
            "session_id": new_uid,
            "clone_root_uuid": uuid_map.get(clone_root_uuid) if clone_root_uuid else None,
        }
        save_object_metadata(ObjectMetadata(**fields))
    return len(uuid_map)


def restore_project_archive(zip_path: Path, user_id: str) -> str:
    """Recreate a project (fresh project/room/object ids) from an exported zip, owned by *user_id*.

    A project-name collision auto-suffixes (`"<name> (2)"`, `(3)`, ...)
    rather than failing -- import never has to negotiate a name with the
    caller first.

    Returns:
        The new project id.

    Raises:
        ArchiveFormatError: When the zip has no manifest, or an unsupported format.
    """
    storage_dir = get_image_storage_dir()
    glb_dir = get_3d_storage_dir()

    with zipfile.ZipFile(zip_path, "r") as zf:
        manifest = _read_manifest(zf)

        base_name = (manifest.get("project") or {}).get("name") or "Imported project"
        project_id: str | None = None
        candidate = base_name
        attempt = 1
        while project_id is None:
            try:
                project_id = project_repo.create_project(user_id, candidate)
            except ValueError:
                attempt += 1
                candidate = f"{base_name} ({attempt})"

        room_count = 0
        object_count = 0
        file_count = 0
        for room in manifest.get("rooms", []):
            old_uid = room["uid"]
            new_uid = str(uuid.uuid4())
            session_repo.register_uid(new_uid, user_id, project_id)

            file_count += _restore_room_files(
                zf, old_uid=old_uid, new_uid=new_uid, storage_dir=storage_dir, glb_dir=glb_dir
            )
            object_count += _restore_room_objects(room, new_uid)
            session_repo.restore_session_state(
                new_uid,
                name=room.get("name"),
                last_changed=room.get("last_changed"),
                history_min=room.get("history_min", 0),
                history_cursor=room.get("history_cursor", 0),
                history_head=room.get("history_head", 0),
            )
            room_count += 1

    logger.info(
        "Project archive restored: project_id=%s name=%r rooms=%d objects=%d files=%d",
        project_id,
        candidate,
        room_count,
        object_count,
        file_count,
    )
    return project_id
