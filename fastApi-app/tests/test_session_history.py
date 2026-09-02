"""Tests for background history commit/undo/redo and API endpoints."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

import settings  # noqa: E402
from core.object_metadata import (  # noqa: E402
    create_object_metadata,
    list_object_ids,
    save_object_metadata,
)
from core.object_storage import (  # noqa: E402
    background_history_path,
    current_background_path,
    object_cutout_path,
)
from core.repositories import session_repo  # noqa: E402
from core.session_history import (  # noqa: E402
    BACKGROUND_HISTORY_LIMIT,
    commit_background,
    get_history_flags,
    redo_background,
    undo_background,
)
from db.models import SessionRow  # noqa: E402
from db.session import session_scope  # noqa: E402


@pytest.fixture
def storage_sandbox(monkeypatch: pytest.MonkeyPatch) -> Path:
    root = Path(tempfile.mkdtemp(prefix="avroom_session_history_"))
    images_dir = root / "images"
    glb_dir = root / "3d"
    images_dir.mkdir(parents=True, exist_ok=True)
    glb_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(images_dir))
    monkeypatch.setattr("api.routes.get_3d_storage_dir", lambda: glb_dir)
    monkeypatch.setattr("core.session_history.get_3d_storage_dir", lambda: glb_dir)
    return images_dir


def _png_bytes(color: tuple[int, int, int] = (10, 20, 30)) -> bytes:
    image = np.zeros((8, 8, 3), dtype=np.uint8)
    image[:, :] = color
    success, encoded = cv2.imencode(".png", image)
    assert success
    return encoded.tobytes()


def _register_session(uid: str = "sess-1") -> None:
    session_repo.register_uid(uid)


def test_commit_then_undo_restores_previous_bytes(storage_sandbox: Path) -> None:
    uid = "sess-1"
    _register_session(uid)
    first = _png_bytes((1, 2, 3))
    second = _png_bytes((4, 5, 6))

    commit_background(uid, first, storage_sandbox)
    commit_background(uid, second, storage_sandbox)
    assert current_background_path(storage_sandbox, uid).read_bytes() == second

    undo_background(uid, storage_sandbox)
    assert current_background_path(storage_sandbox, uid).read_bytes() == first
    flags = get_history_flags(uid)
    assert flags.can_undo is False
    assert flags.can_redo is True


def test_first_inpaint_undo_deletes_live_background(storage_sandbox: Path) -> None:
    uid = "sess-1"
    _register_session(uid)
    commit_background(uid, _png_bytes(), storage_sandbox)
    assert current_background_path(storage_sandbox, uid).exists()

    undo_background(uid, storage_sandbox)
    assert not current_background_path(storage_sandbox, uid).exists()


def test_redo_restores_forward_stage(storage_sandbox: Path) -> None:
    uid = "sess-1"
    _register_session(uid)
    first = _png_bytes((1, 2, 3))
    second = _png_bytes((4, 5, 6))
    commit_background(uid, first, storage_sandbox)
    commit_background(uid, second, storage_sandbox)

    undo_background(uid, storage_sandbox)
    redo_background(uid, storage_sandbox)
    assert current_background_path(storage_sandbox, uid).read_bytes() == second


def test_branch_dump_removes_forward_objects(storage_sandbox: Path) -> None:
    uid = "sess-1"
    _register_session(uid)
    commit_background(uid, _png_bytes((1, 1, 1)), storage_sandbox)
    cursor_one = get_history_flags(uid).history_cursor
    meta_one = create_object_metadata(
        session_id=uid,
        object_id=0,
        average_depth=1.0,
        content_hash="hash-0",
        stage_seq=cursor_one,
    )
    save_object_metadata(meta_one)
    object_cutout_path(storage_sandbox, uid, 0).write_bytes(_png_bytes())

    commit_background(uid, _png_bytes((2, 2, 2)), storage_sandbox)
    cursor_two = get_history_flags(uid).history_cursor
    meta_two = create_object_metadata(
        session_id=uid,
        object_id=1,
        average_depth=1.0,
        content_hash="hash-1",
        stage_seq=cursor_two,
    )
    save_object_metadata(meta_two)
    object_cutout_path(storage_sandbox, uid, 1).write_bytes(_png_bytes())

    undo_background(uid, storage_sandbox)
    assert list_object_ids(uid, visible_only=True) == [0]

    commit_background(uid, _png_bytes((3, 3, 3)), storage_sandbox)
    assert list_object_ids(uid, visible_only=False) == [0]
    assert list_object_ids(uid, visible_only=True) == [0]
    assert not object_cutout_path(storage_sandbox, uid, 1).exists()


def test_fifth_commit_evicts_oldest_snapshot(storage_sandbox: Path) -> None:
    uid = "sess-1"
    _register_session(uid)
    colors = [(i, i, i) for i in range(1, 7)]
    for color in colors:
        commit_background(uid, _png_bytes(color), storage_sandbox)

    with session_scope() as db:
        row = db.get(SessionRow, uid)
        assert row is not None
        assert row.history_cursor - row.history_min == BACKGROUND_HISTORY_LIMIT
        assert not background_history_path(storage_sandbox, uid, row.history_min - 1).exists()


def test_undo_redo_api_endpoints(storage_sandbox: Path) -> None:
    from fastapi.testclient import TestClient

    from main import app

    uid = "sess-1"
    _register_session(uid)
    commit_background(uid, _png_bytes((1, 1, 1)), storage_sandbox)
    commit_background(uid, _png_bytes((2, 2, 2)), storage_sandbox)

    client = TestClient(app)
    cache = client.get(f"/images/{uid}/cache").json()
    assert cache["can_undo"] is True
    assert cache["can_redo"] is False

    undo = client.post(f"/images/{uid}/history/undo")
    assert undo.status_code == 204
    cache = client.get(f"/images/{uid}/cache").json()
    assert cache["can_undo"] is False
    assert cache["can_redo"] is True
    assert current_background_path(storage_sandbox, uid).read_bytes() == _png_bytes((1, 1, 1))

    redo = client.post(f"/images/{uid}/history/redo")
    assert redo.status_code == 204
    assert current_background_path(storage_sandbox, uid).read_bytes() == _png_bytes((2, 2, 2))


def test_objects_list_marks_future_stage_objects_beyond_stage(storage_sandbox: Path) -> None:
    from fastapi.testclient import TestClient

    from main import app

    uid = "sess-1"
    _register_session(uid)
    commit_background(uid, _png_bytes((1, 1, 1)), storage_sandbox)
    cursor = get_history_flags(uid).history_cursor
    meta = create_object_metadata(
        session_id=uid,
        object_id=0,
        average_depth=1.0,
        content_hash="hash",
        stage_seq=cursor,
    )
    save_object_metadata(meta)
    object_cutout_path(storage_sandbox, uid, 0).write_bytes(_png_bytes())

    client = TestClient(app)
    assert client.get(f"/images/{uid}/objects").json()["objects"][0]["beyond_stage"] is False

    undo_background(uid, storage_sandbox)
    response = client.get(f"/images/{uid}/objects").json()
    assert len(response["objects"]) == 1
    assert response["objects"][0]["beyond_stage"] is True

    redo_background(uid, storage_sandbox)
    response = client.get(f"/images/{uid}/objects").json()
    assert len(response["objects"]) == 1
    assert response["objects"][0]["beyond_stage"] is False

    undo_background(uid, storage_sandbox)
    commit_background(uid, _png_bytes((3, 3, 3)), storage_sandbox)
    assert list_object_ids(uid, visible_only=False) == []
    assert not object_cutout_path(storage_sandbox, uid, 0).exists()
