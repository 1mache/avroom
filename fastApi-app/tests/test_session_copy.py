"""Tests for POST /images/{uid}/copy and session_clone helpers."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest
from sqlalchemy import select

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

import settings  # noqa: E402
from core.auth.single_user import LOCAL_USER_ID  # noqa: E402
from core.mask_cache import refined_mask_path  # noqa: E402
from core.object_metadata import (  # noqa: E402
    create_object_metadata,
    get_object_by_uuid,
    list_object_ids,
    load_object_metadata,
    save_object_metadata,
)
from core.object_storage import (  # noqa: E402
    current_background_path,
    object_cutout_path,
    object_glb_path,
    session_preview_path,
)
from core.repositories import job_repo, session_repo  # noqa: E402
from core.session_clone import allocate_copy_room_name, clone_session  # noqa: E402
from db.models import SessionRow  # noqa: E402
from db.session import session_scope  # noqa: E402


@pytest.fixture
def storage_sandbox(monkeypatch: pytest.MonkeyPatch) -> Path:
    root = Path(tempfile.mkdtemp(prefix="avroom_session_copy_"))
    images_dir = root / "images"
    glb_dir = root / "3d"
    images_dir.mkdir(parents=True, exist_ok=True)
    glb_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(images_dir))
    monkeypatch.setattr("core.session_clone.get_3d_storage_dir", lambda: glb_dir)
    monkeypatch.setattr("core.session_teardown.get_3d_storage_dir", lambda: glb_dir)
    assert settings.get_image_storage_dir() == images_dir
    return images_dir


@pytest.fixture
def glb_dir(storage_sandbox: Path) -> Path:
    return storage_sandbox.parent / "3d"


def _write_png(path: Path, *, color: tuple[int, int, int, int] = (10, 20, 30, 255)) -> bytes:
    image = np.zeros((4, 4, 4), dtype=np.uint8)
    image[:, :] = color
    success, encoded = cv2.imencode(".png", image)
    assert success
    data = encoded.tobytes()
    path.write_bytes(data)
    return data


def _write_jpg(path: Path) -> None:
    image = np.zeros((8, 8, 3), dtype=np.uint8)
    image[:, :] = (40, 50, 60)
    success, encoded = cv2.imencode(".jpg", image)
    assert success
    path.write_bytes(encoded.tobytes())


def _seed_room(
    images_dir: Path,
    glb_dir: Path,
    *,
    uid: str = "room-src",
    name: str | None = "Living room",
    with_object: bool = True,
    with_glb: bool = True,
) -> str | None:
    """Create a minimal room on disk + DB. Returns object uuid when with_object."""
    # register_uid without user_id provisions the local dev user + My Rooms project.
    session_repo.register_uid(uid)
    if name is not None:
        session_repo.set_session_name(uid, name)

    _write_jpg(images_dir / f"{uid}.jpg")
    _write_png(current_background_path(images_dir, uid), color=(1, 2, 3, 255))
    _write_jpg(session_preview_path(images_dir, uid))

    if not with_object:
        session_repo.touch_session(uid)
        return None

    _write_png(object_cutout_path(images_dir, uid, 0), color=(9, 8, 7, 255))
    if with_glb:
        object_glb_path(glb_dir, uid, 0).write_bytes(b"fake-glb")

    meta = create_object_metadata(
        session_id=uid,
        object_id=0,
        average_depth=120.5,
        content_hash="abc123",
        source_elevation_deg=18.0,
        name="Chair",
    )
    meta = meta.model_copy(update={"offset_x": 12.0, "offset_y": -4.0, "display_scale": 1.25})
    save_object_metadata(meta)
    session_repo.touch_session(uid)
    return meta.uuid


def _client() -> Any:
    from fastapi.testclient import TestClient
    from main import app

    return TestClient(app)


def test_allocate_copy_room_name_suffixes(storage_sandbox: Path) -> None:
    session_repo.register_uid("seed")
    with session_scope() as db:
        row = db.get(SessionRow, "seed")
        assert row is not None
        project_id = row.project_id

    assert allocate_copy_room_name(project_id, "Living room") == "Living room-copy"

    session_repo.register_uid("a", project_id=project_id)
    session_repo.set_session_name("a", "Living room-copy")
    assert allocate_copy_room_name(project_id, "Living room") == "Living room-copy1"

    session_repo.register_uid("b", project_id=project_id)
    session_repo.set_session_name("b", "Living room-copy1")
    assert allocate_copy_room_name(project_id, "Living room") == "Living room-copy2"

    assert allocate_copy_room_name(project_id, None) == "Untitled room-copy"


def test_clone_session_copies_files_and_remaps_uuids(
    storage_sandbox: Path, glb_dir: Path
) -> None:
    source_uuid = _seed_room(storage_sandbox, glb_dir)
    assert source_uuid is not None

    # Mask candidate + job must NOT be copied.
    refined_mask_path(storage_sandbox, "room-src", "0").write_bytes(b"mask")
    job_repo.create_job(LOCAL_USER_ID, "room-src", "segment", {"x": 1, "y": 2})

    cloned = clone_session("room-src")
    assert cloned.name == "Living room-copy"
    assert cloned.uid != "room-src"

    assert (storage_sandbox / f"{cloned.uid}.jpg").exists()
    assert current_background_path(storage_sandbox, cloned.uid).exists()
    assert session_preview_path(storage_sandbox, cloned.uid).exists()
    assert object_cutout_path(storage_sandbox, cloned.uid, 0).exists()
    assert object_glb_path(glb_dir, cloned.uid, 0).read_bytes() == b"fake-glb"

    assert not refined_mask_path(storage_sandbox, cloned.uid, "0").exists()

    dest_ids = list_object_ids(cloned.uid)
    assert dest_ids == [0]
    dest_meta = load_object_metadata(cloned.uid, 0)
    assert dest_meta is not None
    assert dest_meta.uuid != source_uuid
    assert dest_meta.name == "Chair"
    assert dest_meta.offset_x == 12.0
    assert dest_meta.offset_y == -4.0
    assert dest_meta.display_scale == 1.25
    assert dest_meta.stage_seq == 0
    assert get_object_by_uuid(source_uuid) is not None

    source_jobs = job_repo.list_session_jobs(LOCAL_USER_ID, "room-src")
    assert len(source_jobs) == 1
    assert job_repo.list_session_jobs(LOCAL_USER_ID, cloned.uid) == []


def test_clone_session_second_copy_gets_copy1(storage_sandbox: Path, glb_dir: Path) -> None:
    _seed_room(storage_sandbox, glb_dir)
    first = clone_session("room-src")
    second = clone_session("room-src")
    assert first.name == "Living room-copy"
    assert second.name == "Living room-copy1"


def test_copy_endpoint_returns_session_info(storage_sandbox: Path, glb_dir: Path) -> None:
    _seed_room(storage_sandbox, glb_dir)
    response = _client().post("/images/room-src/copy")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Living room-copy"
    assert body["uid"] != "room-src"
    assert body["last_changed"]


def test_copy_endpoint_404_for_unknown_uid(storage_sandbox: Path) -> None:
    response = _client().post("/images/does-not-exist/copy")
    assert response.status_code == 404


def test_clone_rollback_clears_db_and_files(
    storage_sandbox: Path, glb_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_room(storage_sandbox, glb_dir)

    def boom(*_args: Any, **_kwargs: Any) -> int:
        raise RuntimeError("forced failure")

    monkeypatch.setattr("core.session_clone._clone_visible_objects", boom)

    with pytest.raises(RuntimeError, match="forced failure"):
        clone_session("room-src")

    leftover = [
        p for p in storage_sandbox.iterdir() if p.is_file() and not p.name.startswith("room-src")
    ]
    assert leftover == [], leftover

    with session_scope() as db:
        extras = list(
            db.execute(select(SessionRow.id).where(SessionRow.id != "room-src")).scalars().all()
        )
    assert extras == []
    assert session_repo.is_session_registered("room-src")
