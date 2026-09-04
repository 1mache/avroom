"""Tests for `core/project_archive.py` (export/import) and its two routes.

Mirrors `tests/test_object_import.py`'s storage_sandbox pattern. Core-level
tests exercise `build_project_archive`/`restore_project_archive` directly
(faster, and lets assertions reach into DB state without an HTTP round
trip); one endpoint-level test proves `api/projects.py`'s wiring works.
"""

from __future__ import annotations

import json
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

import settings  # noqa: E402
from core.auth.single_user import LOCAL_USER_ID  # noqa: E402
from core.object_metadata import (  # noqa: E402
    build_clone_metadata,
    create_object_metadata,
    load_object_metadata,
    next_object_id,
    save_object_metadata,
)
from core.object_storage import (  # noqa: E402
    current_background_path,
    object_cutout_path,
    object_glb_path,
    session_preview_path,
)
from core.project_archive import ArchiveFormatError, build_project_archive, restore_project_archive  # noqa: E402
from core.repositories import project_repo, session_repo  # noqa: E402
from core.session_history import commit_background  # noqa: E402


@pytest.fixture(autouse=True)
def _single_user_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force AUTH_MODE=single_user regardless of a dev machine's own .env --
    see test_admin_gate.py's identical fixture for the rationale."""
    monkeypatch.setenv("AUTH_MODE", "single_user")


@dataclass
class StorageSandbox:
    images: Path
    glb: Path


@pytest.fixture
def storage_sandbox(monkeypatch: pytest.MonkeyPatch) -> StorageSandbox:
    root = Path(tempfile.mkdtemp(prefix="avroom_project_archive_"))
    images_dir = root / "images"
    glb_dir = root / "3d"
    images_dir.mkdir(parents=True, exist_ok=True)
    glb_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(images_dir))
    monkeypatch.setattr("core.project_archive.get_3d_storage_dir", lambda: glb_dir)
    monkeypatch.setattr("core.session_teardown.get_3d_storage_dir", lambda: glb_dir)
    assert settings.get_image_storage_dir() == images_dir
    return StorageSandbox(images=images_dir, glb=glb_dir)


def _seed_room(sandbox: StorageSandbox, *, uid: str, project_id: str, object_count: int = 1) -> None:
    """Register a room with a background, undo history, and *object_count* objects
    (object 1, if requested, is a clone of object 0), each with a cutout + GLB."""
    session_repo.register_uid(uid, LOCAL_USER_ID, project_id)
    (sandbox.images / f"{uid}.png").write_bytes(b"original-bytes")
    commit_background(uid, b"canvas-v1", sandbox.images)
    commit_background(uid, b"canvas-v2", sandbox.images)  # leaves one _bg_hist_1.png behind
    session_preview_path(sandbox.images, uid).write_bytes(b"preview-bytes")

    root_meta = create_object_metadata(
        session_id=uid, object_id=0, average_depth=0.5, content_hash="hash0"
    )
    save_object_metadata(root_meta)
    object_cutout_path(sandbox.images, uid, 0).write_bytes(b"cutout-0")
    object_glb_path(sandbox.glb, uid, 0).write_bytes(b"glb-0")

    if object_count > 1:
        clone_meta = build_clone_metadata(root_meta, next_object_id(uid))
        save_object_metadata(clone_meta)
        object_cutout_path(sandbox.images, uid, clone_meta.object_id).write_bytes(b"cutout-1")


def _seed_project(sandbox: StorageSandbox, *, name: str = "Apartment") -> tuple[str, list[str]]:
    session_repo.register_uid("bootstrap")  # provisions the local user row
    project_id = project_repo.create_project(LOCAL_USER_ID, name)
    room_a, room_b = "room-a", "room-b"
    _seed_room(sandbox, uid=room_a, project_id=project_id, object_count=2)
    _seed_room(sandbox, uid=room_b, project_id=project_id, object_count=1)
    return project_id, [room_a, room_b]


def test_round_trip_preserves_files_and_metadata(storage_sandbox: StorageSandbox, tmp_path: Path) -> None:
    project_id, (room_a, room_b) = _seed_project(storage_sandbox)
    old_clone = load_object_metadata(room_a, 1)
    assert old_clone is not None and old_clone.clone_root_uuid is not None

    zip_path = tmp_path / "export.zip"
    build_project_archive(project_id, zip_path)

    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert "manifest.json" in names
        assert not any("_depth_" in n or "_normal_" in n or "_mask_" in n for n in names)

    new_project_id = restore_project_archive(zip_path, LOCAL_USER_ID)
    assert new_project_id != project_id

    new_rooms = project_repo.list_project_session_ids(new_project_id)
    assert len(new_rooms) == 2
    assert room_a not in new_rooms and room_b not in new_rooms

    for new_uid in new_rooms:
        assert (storage_sandbox.images / f"{new_uid}.png").exists()
        assert current_background_path(storage_sandbox.images, new_uid).exists()
        assert list(storage_sandbox.images.glob(f"{new_uid}_bg_hist_*.png"))
        assert session_preview_path(storage_sandbox.images, new_uid).exists()
        assert object_cutout_path(storage_sandbox.images, new_uid, 0).exists()
        assert object_glb_path(storage_sandbox.glb, new_uid, 0).exists()

        state = session_repo.get_session_state(new_uid)
        assert state is not None
        assert state.history_cursor == 2
        assert state.history_head == 2

    # Find the room that had the clone (object 1) and check lineage remap.
    cloned_room = next(uid for uid in new_rooms if load_object_metadata(uid, 1) is not None)
    new_clone = load_object_metadata(cloned_room, 1)
    new_root = load_object_metadata(cloned_room, 0)
    assert new_clone is not None and new_root is not None
    assert new_clone.uuid != old_clone.uuid
    assert new_clone.clone_root_uuid == new_root.uuid  # remapped to the NEW root uuid, not the old one
    assert new_root.content_hash == "hash0"
    assert new_root.average_depth == 0.5


def test_import_autosuffixes_duplicate_name(storage_sandbox: StorageSandbox, tmp_path: Path) -> None:
    project_id, _ = _seed_project(storage_sandbox, name="Apartment")
    zip_path = tmp_path / "export.zip"
    build_project_archive(project_id, zip_path)

    # A project already owns the name "Apartment" (the one we just exported).
    second_id = restore_project_archive(zip_path, LOCAL_USER_ID)
    summary = project_repo.get_project(second_id)
    assert summary is not None
    assert summary.name == "Apartment (2)"


def test_restore_rejects_missing_manifest(tmp_path: Path) -> None:
    zip_path = tmp_path / "bad.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("images/not-a-manifest.txt", "hi")

    with pytest.raises(ArchiveFormatError):
        restore_project_archive(zip_path, LOCAL_USER_ID)


def test_restore_ignores_path_traversal_entries(storage_sandbox: StorageSandbox, tmp_path: Path) -> None:
    session_repo.register_uid("bootstrap-traversal")  # provisions the local user row
    zip_path = tmp_path / "malicious.zip"
    manifest: dict[str, Any] = {
        "format": 1,
        "project": {"name": "Evil"},
        "rooms": [
            {
                "uid": "old-uid",
                "name": None,
                "last_changed": None,
                "history_min": 0,
                "history_cursor": 0,
                "history_head": 0,
                "objects": [],
            }
        ],
    }
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("images/../../evil.png", b"escaped")
        zf.writestr("../also-escaped.png", b"escaped")

    new_project_id = restore_project_archive(zip_path, LOCAL_USER_ID)
    assert new_project_id is not None

    escaped = list(_APP_ROOT.parent.glob("evil.png")) + list(_APP_ROOT.parent.parent.glob("also-escaped.png"))
    assert not escaped


def test_export_and_import_endpoints(storage_sandbox: StorageSandbox) -> None:
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app)

    project_id, _ = _seed_project(storage_sandbox, name="Endpoint room")

    exported = client.get(f"/projects/{project_id}/export")
    assert exported.status_code == 200
    assert exported.headers["content-type"] == "application/zip"

    imported = client.post(
        "/projects/import",
        files={"file": ("export.avroom.zip", exported.content, "application/zip")},
    )
    assert imported.status_code == 201
    body = imported.json()
    assert body["room_count"] == 2
    assert body["id"] != project_id
