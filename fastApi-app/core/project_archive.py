from __future__ import annotations

"""Project and room export/import as a single self-contained zip.

Bundles one or more rooms -- their DB metadata (name, history counters,
object rows) plus every blob they own (original upload, canvas, undo
snapshots, cutouts, GLBs) -- so they can move to a different machine with
fresh session/object/project ids minted on import.

A project archive (`build_project_archive`/`restore_project_archive`) bundles
every room in a project plus a project name. A room archive
(`build_room_archive`/`restore_room_archive`) bundles exactly one room, to be
imported into an existing project. Both share the same manifest shape, blob
layout, and zip-slip guard; the manifest's `kind` field ("project" or "room",
missing == "project" for archives exported before this field existed) is what
lets `_read_manifest` reject a project zip fed to the room importer (or vice
versa) with a clear message instead of a confusing generic one.

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
from core.object_storage import resolve_object_cutout_path
from core.repositories import project_repo, session_repo
from core.repositories.session_repo import SessionNotFoundError
from settings import get_3d_storage_dir, get_image_storage_dir

logger = logging.getLogger(__name__)

ARCHIVE_FORMAT = 1
MANIFEST_NAME = "manifest.json"

KIND_PROJECT = "project"
KIND_ROOM = "room"

_IMAGES_DIR = "images"
_GLB_DIR = "3d"
_SKIP_SUBSTRINGS = ("_depth_", "_normal_", "_mask_")

# Matches exactly one path segment under images/ or 3d/ -- the zip-slip
# guard. Destination paths are built from a freshly minted uid plus this
# validated basename, never by joining an archive-supplied path directly.
_ENTRY_RE = re.compile(r"^(images|3d)/([^/\\]+)$")


class ArchiveFormatError(ValueError):
    """Raised when a zip has no manifest, a malformed one, or an unsupported/wrong-kind format."""


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


def _room_manifest_entry(uid: str) -> dict[str, Any] | None:
    """Build one room's manifest dict (state + every object's metadata).

    Returns `None` if *uid* has vanished since its caller looked it up
    (defensive -- an FK guarantees this can't happen for a project's own
    rooms, but a room archive's single uid is resolved fresh, so this is the
    normal not-found path there too).
    """
    state = session_repo.get_session_state(uid)
    if state is None:
        return None

    objects: list[dict[str, Any]] = []
    for object_id in list_object_ids(uid):
        metadata = load_object_metadata(uid, object_id)
        if metadata is not None:
            objects.append(metadata.model_dump())

    return {
        "uid": uid,
        "name": state.name,
        "created_at": state.created_at,
        "last_changed": state.last_changed,
        "history_min": state.history_min,
        "history_cursor": state.history_cursor,
        "history_head": state.history_head,
        "objects": objects,
    }


def _write_archive(rooms_manifest: list[dict[str, Any]], room_ids: list[str], extra: dict[str, Any], out_path: Path) -> int:
    """Write `manifest.json` plus every room's blobs to *out_path*. Returns file count."""
    storage_dir = get_image_storage_dir()
    glb_dir = get_3d_storage_dir()
    file_count = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_STORED) as zf:
        for uid in room_ids:
            for source_path, archive_name in _room_blob_paths(storage_dir, glb_dir, uid):
                zf.write(source_path, archive_name)
                file_count += 1
        manifest = {
            "format": ARCHIVE_FORMAT,
            "exported_at": datetime.now(UTC).isoformat(),
            "rooms": rooms_manifest,
            **extra,
        }
        zf.writestr(MANIFEST_NAME, json.dumps(manifest))
    return file_count


def build_project_archive(project_id: str, out_path: Path) -> None:
    """Write a project (every room, its metadata, and its blobs) to a zip at *out_path*.

    Raises:
        project_repo.ProjectNotFoundError: When *project_id* doesn't exist.
    """
    summary = project_repo.get_project(project_id)
    if summary is None:
        raise project_repo.ProjectNotFoundError(project_id)

    room_ids = project_repo.list_project_session_ids(project_id)
    rooms_manifest: list[dict[str, Any]] = []
    kept_ids: list[str] = []
    for uid in room_ids:
        entry = _room_manifest_entry(uid)
        if entry is None:  # pragma: no cover - defensive; FK guarantees this can't happen
            logger.warning("Project archive: room vanished mid-export, skipping: uid=%s", uid)
            continue
        rooms_manifest.append(entry)
        kept_ids.append(uid)

    file_count = _write_archive(
        rooms_manifest, kept_ids, {"kind": KIND_PROJECT, "project": {"name": summary.name}}, out_path
    )

    logger.info(
        "Project archive built: project_id=%s rooms=%d files=%d out_path=%s",
        project_id,
        len(kept_ids),
        file_count,
        out_path,
    )


def build_room_archive(uid: str, out_path: Path) -> None:
    """Write one room (its metadata and blobs) to a zip at *out_path*.

    Raises:
        session_repo.SessionNotFoundError: When *uid* isn't registered.
    """
    entry = _room_manifest_entry(uid)
    if entry is None:
        raise SessionNotFoundError(uid)

    file_count = _write_archive([entry], [uid], {"kind": KIND_ROOM}, out_path)

    logger.info("Room archive built: uid=%s files=%d out_path=%s", uid, file_count, out_path)


def archive_filename(name: str, *, kind: str) -> str:
    """Sanitize a project/room name for use as a downloaded zip's filename."""
    cleaned = "".join(ch if ch not in '<>:"/\\|?*' else "_" for ch in name.strip())
    suffix = "avroom.zip" if kind == KIND_PROJECT else "avroom-room.zip"
    fallback = "project" if kind == KIND_PROJECT else "room"
    return f"{cleaned[:80] or fallback}.{suffix}"


def _read_manifest(zf: zipfile.ZipFile, expected_kind: str) -> dict[str, Any]:
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

    kind = manifest.get("kind", KIND_PROJECT)  # archives predating this field are projects
    if kind not in (KIND_PROJECT, KIND_ROOM):
        raise ArchiveFormatError(f"Unsupported archive kind: {kind!r}")
    if kind != expected_kind:
        if kind == KIND_ROOM:
            raise ArchiveFormatError(
                "This is a room export, not a project export. Open a project and use Import room instead."
            )
        raise ArchiveFormatError(
            "This is a project export, not a room export. Go back to Projects and use Import project instead."
        )
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


def _classify_is_3d(storage_dir: Path, uid: str, object_id: int) -> bool:
    """Best-effort shape classify for an object whose archived ``is_3d`` is null.

    Only object creation (`image_processing.py`, `object_import.py`) ever runs
    the classifier -- an export made before that field existed carries `null`
    forever otherwise, since nothing else revisits it post-creation.
    """
    try:
        from core.avroom_package import load_avroom_attr
        from core.image_processing import _get_cutout_clip_scorer

        cutout_path = resolve_object_cutout_path(storage_dir, uid, object_id)
        classify_png = load_avroom_attr(
            "classify_object_is_3d_from_png_bytes",
            "avroom_object_removal.core.object_shape_classifier",
        )
        return bool(classify_png(cutout_path.read_bytes(), scorer=_get_cutout_clip_scorer()))
    except Exception:
        logger.exception(
            "Object shape classify failed on import; defaulting is_3d=True: "
            "session_id=%s object_id=%d",
            uid,
            object_id,
        )
        return True


def _restore_room_objects(room: dict[str, Any], new_uid: str, storage_dir: Path) -> int:
    """Persist every object in *room* under *new_uid*, with fresh uuids and remapped clone lineage."""
    uuid_map = {obj["uuid"]: str(uuid.uuid4()) for obj in room.get("objects", [])}
    for obj in room.get("objects", []):
        clone_root_uuid = obj.get("clone_root_uuid")
        is_3d = obj.get("is_3d")
        if is_3d is None:
            is_3d = _classify_is_3d(storage_dir, new_uid, obj["object_id"])
        fields = {
            **obj,
            "uuid": uuid_map[obj["uuid"]],
            "session_id": new_uid,
            "clone_root_uuid": uuid_map.get(clone_root_uuid) if clone_root_uuid else None,
            "is_3d": is_3d,
        }
        save_object_metadata(ObjectMetadata(**fields))
    return len(uuid_map)


def _restore_room(zf: zipfile.ZipFile, room: dict[str, Any], user_id: str, project_id: str) -> str:
    """Recreate one manifest room entry under a fresh uid inside *project_id*.

    Resolves a room-name collision (names are unique per project, unlike
    project names which are unique per user and can't collide into a
    brand-new project) by falling back to `session_clone.allocate_copy_room_name`
    -- the same `"<name>-copy"` scheme a manual room copy uses. Returns the
    new uid.
    """
    storage_dir = get_image_storage_dir()
    glb_dir = get_3d_storage_dir()

    old_uid = room["uid"]
    new_uid = str(uuid.uuid4())
    session_repo.register_uid(new_uid, user_id, project_id)

    _restore_room_files(zf, old_uid=old_uid, new_uid=new_uid, storage_dir=storage_dir, glb_dir=glb_dir)
    _restore_room_objects(room, new_uid, storage_dir)

    name = room.get("name")
    if name is not None:
        try:
            session_repo.set_session_name(new_uid, name)
        except ValueError:
            from core.session_clone import allocate_copy_room_name

            name = allocate_copy_room_name(project_id, name)
            session_repo.set_session_name(new_uid, name)

    session_repo.restore_session_state(
        new_uid,
        name=name,
        last_changed=room.get("last_changed"),
        history_min=room.get("history_min", 0),
        history_cursor=room.get("history_cursor", 0),
        history_head=room.get("history_head", 0),
    )
    return new_uid


def restore_project_archive(zip_path: Path, user_id: str) -> str:
    """Recreate a project (fresh project/room/object ids) from an exported zip, owned by *user_id*.

    A project-name collision auto-suffixes (`"<name> (2)"`, `(3)`, ...)
    rather than failing -- import never has to negotiate a name with the
    caller first.

    Returns:
        The new project id.

    Raises:
        ArchiveFormatError: When the zip has no manifest, or is a wrong-kind/unsupported format.
    """
    with zipfile.ZipFile(zip_path, "r") as zf:
        manifest = _read_manifest(zf, KIND_PROJECT)

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
        for room in manifest.get("rooms", []):
            _restore_room(zf, room, user_id, project_id)
            room_count += 1

    logger.info(
        "Project archive restored: project_id=%s name=%r rooms=%d",
        project_id,
        candidate,
        room_count,
    )
    return project_id


def restore_room_archive(zip_path: Path, user_id: str, project_id: str) -> str:
    """Recreate one room (fresh room/object ids) from an exported zip, inside *project_id*.

    Raises:
        ArchiveFormatError: When the zip has no manifest, or is a wrong-kind/unsupported format.

    Returns:
        The new room's uid.
    """
    with zipfile.ZipFile(zip_path, "r") as zf:
        manifest = _read_manifest(zf, KIND_ROOM)
        rooms = manifest.get("rooms", [])
        if not rooms:
            raise ArchiveFormatError("Room archive has no room entry")
        new_uid = _restore_room(zf, rooms[0], user_id, project_id)

    logger.info("Room archive restored: uid=%s project_id=%s", new_uid, project_id)
    return new_uid
