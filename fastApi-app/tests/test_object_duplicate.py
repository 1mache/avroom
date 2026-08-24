"""Tests for POST /images/objects/{uuid}/duplicate and clone helpers."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import cv2
import numpy as np
import pytest

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

import settings  # noqa: E402
from core.repositories import session_repo  # noqa: E402
from core.object_metadata import (  # noqa: E402
    create_object_metadata,
    format_clone_name,
    get_object_by_uuid,
    list_object_ids,
    save_object_metadata,
)
from core.object_storage import (  # noqa: E402
    object_cutout_path,
    object_glb_path,
)


@pytest.fixture
def storage_sandbox(monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect image + 3D storage and sidecars to an isolated directory."""

    root = Path(tempfile.mkdtemp(prefix="avroom_object_duplicate_"))
    images_dir = root / "images"
    glb_dir = root / "3d"
    images_dir.mkdir(parents=True, exist_ok=True)
    glb_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(images_dir))
    monkeypatch.setattr("api.routes.get_3d_storage_dir", lambda: glb_dir)
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


def _seed_object(
    images_dir: Path,
    glb_dir: Path,
    *,
    uid: str = "sess-1",
    object_id: int = 0,
    name: str | None = "Chair",
    with_glb: bool = True,
    content_hash: str = "abc123",
) -> str:
    """Create cutout (+ optional GLB) and metadata; return object uuid."""

    cutout_bytes = _write_png(object_cutout_path(images_dir, uid, object_id))
    if with_glb:
        object_glb_path(glb_dir, uid, object_id).write_bytes(b"fake-glb")

    meta = create_object_metadata(
        session_id=uid,
        object_id=object_id,
        average_depth=120.5,
        content_hash=content_hash,
        source_elevation_deg=18.0,
        name=name,
    )
    save_object_metadata(meta)
    assert cutout_bytes
    return meta.uuid


def _build_client() -> Any:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_format_clone_name() -> None:
    assert format_clone_name("Chair", 0) == "Chair-copy"
    assert format_clone_name("Chair", 1) == "Chair-copy1"
    assert format_clone_name("Object 0", 2) == "Object 0-copy2"


def test_duplicate_copies_all_artifacts_and_returns_new_uuid(
    storage_sandbox: Path, glb_dir: Path
) -> None:
    session_repo.register_uid("sess-1")
    before = session_repo.touch_session("sess-1")
    source_uuid = _seed_object(storage_sandbox, glb_dir)

    with _build_client() as client:
        response = client.post(f"/images/objects/{source_uuid}/duplicate")

    assert response.status_code == 200
    body = response.json()
    clone_uuid = body["object_uuid"]
    assert clone_uuid != source_uuid

    clone = get_object_by_uuid(clone_uuid)
    assert clone is not None
    assert clone.object_id == 1
    assert clone.name == "Chair-copy"
    assert clone.average_depth == 120.5
    assert clone.content_hash == "abc123"
    assert clone.source_elevation_deg == 18.0
    assert clone.clone_root_uuid == source_uuid
    assert clone.clone_root_label == "Chair"
    assert clone.clone_index == 0

    source_cutout = object_cutout_path(storage_sandbox, "sess-1", 0).read_bytes()
    clone_cutout = object_cutout_path(storage_sandbox, "sess-1", 1).read_bytes()
    assert clone_cutout == source_cutout

    assert object_glb_path(glb_dir, "sess-1", 1).read_bytes() == b"fake-glb"

    after = session_repo.get_session_last_changed("sess-1")
    assert after is not None
    assert after >= before


def test_duplicate_without_optional_artifacts(storage_sandbox: Path, glb_dir: Path) -> None:
    source_uuid = _seed_object(storage_sandbox, glb_dir, with_glb=False)

    with _build_client() as client:
        response = client.post(f"/images/objects/{source_uuid}/duplicate")

    assert response.status_code == 200
    clone_uuid = response.json()["object_uuid"]
    clone = get_object_by_uuid(clone_uuid)
    assert clone is not None
    assert object_cutout_path(storage_sandbox, "sess-1", 1).exists()
    assert not object_glb_path(glb_dir, "sess-1", 1).exists()


def test_copy_naming_sequence_and_unnamed_fallback(
    storage_sandbox: Path, glb_dir: Path
) -> None:
    named_uuid = _seed_object(storage_sandbox, glb_dir, object_id=0, name="Chair")
    unnamed_uuid = _seed_object(
        storage_sandbox,
        glb_dir,
        object_id=1,
        name=None,
        with_glb=False,
        content_hash="hash-unnamed",
    )

    with _build_client() as client:
        first = client.post(f"/images/objects/{named_uuid}/duplicate")
        second = client.post(f"/images/objects/{named_uuid}/duplicate")
        third_from_clone = client.post(
            f"/images/objects/{first.json()['object_uuid']}/duplicate"
        )
        unnamed_copy = client.post(f"/images/objects/{unnamed_uuid}/duplicate")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third_from_clone.status_code == 200
    assert unnamed_copy.status_code == 200

    first_meta = get_object_by_uuid(first.json()["object_uuid"])
    second_meta = get_object_by_uuid(second.json()["object_uuid"])
    third_meta = get_object_by_uuid(third_from_clone.json()["object_uuid"])
    unnamed_meta = get_object_by_uuid(unnamed_copy.json()["object_uuid"])

    assert first_meta is not None and first_meta.name == "Chair-copy"
    assert second_meta is not None and second_meta.name == "Chair-copy1"
    assert third_meta is not None and third_meta.name == "Chair-copy2"
    assert third_meta.clone_root_uuid == named_uuid
    assert unnamed_meta is not None and unnamed_meta.name == "Object 1-copy"


def test_renamed_clone_keeps_root_label_for_next_copy(
    storage_sandbox: Path, glb_dir: Path
) -> None:
    source_uuid = _seed_object(storage_sandbox, glb_dir, name="Chair")

    with _build_client() as client:
        first = client.post(f"/images/objects/{source_uuid}/duplicate")
        assert first.status_code == 200
        first_uuid = first.json()["object_uuid"]

        rename = client.patch(
            f"/images/objects/{first_uuid}",
            json={"name": "Sofa"},
        )
        assert rename.status_code == 200

        second = client.post(f"/images/objects/{first_uuid}/duplicate")

    assert second.status_code == 200
    second_meta = get_object_by_uuid(second.json()["object_uuid"])
    assert second_meta is not None
    assert second_meta.name == "Chair-copy1"
    assert second_meta.clone_root_label == "Chair"


def test_missing_source_returns_404(storage_sandbox: Path) -> None:
    with _build_client() as client:
        response = client.post("/images/objects/does-not-exist/duplicate")
    assert response.status_code == 404


def test_missing_cutout_returns_404(storage_sandbox: Path, glb_dir: Path) -> None:
    source_uuid = _seed_object(storage_sandbox, glb_dir, with_glb=False)
    object_cutout_path(storage_sandbox, "sess-1", 0).unlink()

    with _build_client() as client:
        response = client.post(f"/images/objects/{source_uuid}/duplicate")

    assert response.status_code == 404
    # Metadata now lives in Postgres, decoupled from the (missing) cutout file:
    # the source object row still legitimately exists at id 0. What matters
    # here is that no orphan clone (id 1) got created.
    assert list_object_ids("sess-1") == [0]


def test_failed_copy_rolls_back_partial_files(
    storage_sandbox: Path, glb_dir: Path
) -> None:
    source_uuid = _seed_object(storage_sandbox, glb_dir)

    def _boom(**_kwargs: Any) -> list[Path]:
        # Simulate a failure after a cutout appeared, then let the endpoint clean up.
        dest = object_cutout_path(storage_sandbox, "sess-1", 1)
        dest.write_bytes(b"partial")
        raise RuntimeError("disk full")

    with patch("api.routes.copy_object_artifacts", side_effect=_boom):
        with _build_client() as client:
            response = client.post(f"/images/objects/{source_uuid}/duplicate")

    assert response.status_code == 500
    assert list_object_ids("sess-1") == [0]
    assert not object_cutout_path(storage_sandbox, "sess-1", 1).exists()
    assert not object_glb_path(glb_dir, "sess-1", 1).exists()
    assert get_object_by_uuid(source_uuid) is not None


def test_shared_depth_cache_not_duplicated(storage_sandbox: Path, glb_dir: Path) -> None:
    source_uuid = _seed_object(storage_sandbox, glb_dir, content_hash="depth-hash")
    depth_path = storage_sandbox / "sess-1_depth_depth-hash.npy"
    np.save(depth_path, np.zeros((2, 2), dtype=np.uint8))
    depth_mtime = depth_path.stat().st_mtime

    with _build_client() as client:
        response = client.post(f"/images/objects/{source_uuid}/duplicate")

    assert response.status_code == 200
    assert depth_path.exists()
    assert depth_path.stat().st_mtime == depth_mtime
    assert len(list(storage_sandbox.glob("sess-1_depth_*.npy"))) == 1

    clone = get_object_by_uuid(response.json()["object_uuid"])
    assert clone is not None
    assert clone.content_hash == "depth-hash"


def test_background_untouched(storage_sandbox: Path, glb_dir: Path) -> None:
    bg = storage_sandbox / "sess-1_background.png"
    bg.write_bytes(b"background-bytes")
    source_uuid = _seed_object(storage_sandbox, glb_dir)

    with _build_client() as client:
        response = client.post(f"/images/objects/{source_uuid}/duplicate")

    assert response.status_code == 200
    assert bg.read_bytes() == b"background-bytes"


def _seed_object_with_canvas(
    images_dir: Path,
    glb_dir: Path,
    *,
    canvas_size: int = 100,
    box: tuple[int, int, int, int] = (40, 40, 60, 60),
    offset_x: float = 0.0,
    offset_y: float = 0.0,
    uid: str = "sess-1",
    object_id: int = 0,
) -> str:
    """Seed an object whose cutout has room around its alpha bounds to nudge into.

    *box* is (left, top, right, bottom) of the opaque region within a
    *canvas_size* x *canvas_size* transparent canvas.
    """
    left, top, right, bottom = box
    image = np.zeros((canvas_size, canvas_size, 4), dtype=np.uint8)
    image[top:bottom, left:right] = (10, 20, 30, 255)
    success, encoded = cv2.imencode(".png", image)
    assert success
    object_cutout_path(images_dir, uid, object_id).write_bytes(encoded.tobytes())

    meta = create_object_metadata(
        session_id=uid,
        object_id=object_id,
        average_depth=100.0,
        content_hash="hash",
        source_elevation_deg=15.0,
        name="Chair",
        offset_x=offset_x,
        offset_y=offset_y,
    )
    save_object_metadata(meta)
    return meta.uuid


def test_duplicate_nudges_clone_left_when_room(storage_sandbox: Path, glb_dir: Path) -> None:
    # bounds: left=40, right=60, width=20 -> nudge = max(12, 20*0.15) = 12.
    # min_x = -40, max_x = 100-60 = 40. Source at offset_x=0 has room on the left.
    source_uuid = _seed_object_with_canvas(storage_sandbox, glb_dir, offset_x=0.0, offset_y=0.0)

    with _build_client() as client:
        response = client.post(f"/images/objects/{source_uuid}/duplicate")

    assert response.status_code == 200
    clone = get_object_by_uuid(response.json()["object_uuid"])
    assert clone is not None
    assert clone.offset_x == -12.0
    assert clone.offset_y == 0.0


def test_duplicate_nudges_clone_right_when_no_room_on_left(
    storage_sandbox: Path, glb_dir: Path
) -> None:
    # Source sits flush against the left bound (min_x = -40, offset_x = -40),
    # so a left nudge (-52) would go out of bounds -- must fall back to right.
    source_uuid = _seed_object_with_canvas(storage_sandbox, glb_dir, offset_x=-40.0, offset_y=5.0)

    with _build_client() as client:
        response = client.post(f"/images/objects/{source_uuid}/duplicate")

    assert response.status_code == 200
    clone = get_object_by_uuid(response.json()["object_uuid"])
    assert clone is not None
    assert clone.offset_x == -28.0
    assert clone.offset_y == 5.0


def test_duplicate_keeps_source_offset_when_no_room_either_side(
    storage_sandbox: Path, glb_dir: Path
) -> None:
    # Cutout fills the entire canvas (box == full extent): min_x == max_x == 0,
    # no nudge fits in either direction.
    source_uuid = _seed_object_with_canvas(
        storage_sandbox, glb_dir, canvas_size=10, box=(0, 0, 10, 10), offset_x=3.0, offset_y=-2.0
    )

    with _build_client() as client:
        response = client.post(f"/images/objects/{source_uuid}/duplicate")

    assert response.status_code == 200
    clone = get_object_by_uuid(response.json()["object_uuid"])
    assert clone is not None
    assert clone.offset_x == 3.0
    assert clone.offset_y == -2.0
