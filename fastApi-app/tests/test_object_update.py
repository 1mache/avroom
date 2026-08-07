"""Tests for PATCH /images/objects/{uuid} partial-update semantics (name + offset)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

import settings  # noqa: E402
from core.object_metadata import (  # noqa: E402
    create_object_metadata,
    get_object_by_uuid,
    save_object_metadata,
)
from core.object_storage import object_cutout_path  # noqa: E402


@pytest.fixture
def storage_sandbox(monkeypatch: pytest.MonkeyPatch) -> Path:
    root = Path(tempfile.mkdtemp(prefix="avroom_object_update_"))
    images_dir = root / "images"
    glb_dir = root / "3d"
    images_dir.mkdir(parents=True, exist_ok=True)
    glb_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(images_dir))
    monkeypatch.setattr("api.routes.get_3d_storage_dir", lambda: glb_dir)
    assert settings.get_image_storage_dir() == images_dir
    return images_dir


def _write_png(path: Path) -> None:
    image = np.zeros((4, 4, 4), dtype=np.uint8)
    image[:, :] = (10, 20, 30, 255)
    success, encoded = cv2.imencode(".png", image)
    assert success
    path.write_bytes(encoded.tobytes())


def _seed_object(images_dir: Path, *, uid: str = "sess-1", object_id: int = 0) -> str:
    _write_png(object_cutout_path(images_dir, uid, object_id))
    meta = create_object_metadata(
        session_id=uid,
        object_id=object_id,
        average_depth=100.0,
        content_hash="h1",
        source_elevation_deg=15.0,
        name="Chair",
    )
    save_object_metadata(images_dir, meta)
    return meta.uuid


def _build_client() -> Any:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_offset_only_update_leaves_name_untouched(storage_sandbox: Path) -> None:
    object_uuid = _seed_object(storage_sandbox)

    with _build_client() as client:
        response = client.patch(
            f"/images/objects/{object_uuid}", json={"offset_x": 12.5, "offset_y": -4.0}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["offset_x"] == 12.5
    assert body["offset_y"] == -4.0
    assert body["name"] == "Chair"

    metadata = get_object_by_uuid(storage_sandbox, object_uuid)
    assert metadata is not None
    assert metadata.name == "Chair"
    assert metadata.offset_x == 12.5
    assert metadata.offset_y == -4.0


def test_name_only_update_leaves_offset_untouched(storage_sandbox: Path) -> None:
    object_uuid = _seed_object(storage_sandbox)

    with _build_client() as client:
        # Establish a non-zero offset first.
        client.patch(f"/images/objects/{object_uuid}", json={"offset_x": 30.0, "offset_y": 20.0})
        response = client.patch(f"/images/objects/{object_uuid}", json={"name": "Sofa"})

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Sofa"
    assert body["offset_x"] == 30.0
    assert body["offset_y"] == 20.0


def test_both_name_and_offset_update_together(storage_sandbox: Path) -> None:
    object_uuid = _seed_object(storage_sandbox)

    with _build_client() as client:
        response = client.patch(
            f"/images/objects/{object_uuid}",
            json={"name": "Lamp", "offset_x": 5.0, "offset_y": 5.0},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Lamp"
    assert body["offset_x"] == 5.0
    assert body["offset_y"] == 5.0


def test_name_null_clears_name(storage_sandbox: Path) -> None:
    object_uuid = _seed_object(storage_sandbox)

    with _build_client() as client:
        response = client.patch(f"/images/objects/{object_uuid}", json={"name": None})

    assert response.status_code == 200
    assert response.json()["name"] is None


def test_missing_uuid_returns_404(storage_sandbox: Path) -> None:
    with _build_client() as client:
        response = client.patch("/images/objects/does-not-exist", json={"offset_x": 1.0, "offset_y": 1.0})
    assert response.status_code == 404


def test_update_bumps_last_changed(storage_sandbox: Path) -> None:
    settings.register_uid("sess-1")
    before = settings.touch_session("sess-1")
    object_uuid = _seed_object(storage_sandbox)

    with _build_client() as client:
        response = client.patch(
            f"/images/objects/{object_uuid}", json={"offset_x": 1.0, "offset_y": 1.0}
        )

    assert response.status_code == 200
    after = settings.get_session_last_changed("sess-1")
    assert after is not None
    assert after >= before
