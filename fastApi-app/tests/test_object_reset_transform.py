"""Tests for POST /images/objects/{uuid}/reset-transform."""

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
    set_object_offset,
    set_object_rescale_state,
)
from core.object_storage import object_cutout_path  # noqa: E402


@pytest.fixture
def storage_sandbox(monkeypatch: pytest.MonkeyPatch) -> Path:
    root = Path(tempfile.mkdtemp(prefix="avroom_object_reset_"))
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
    save_object_metadata(meta)
    return meta.uuid


def _build_client() -> Any:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_reset_transform_restores_defaults(storage_sandbox: Path) -> None:
    object_uuid = _seed_object(storage_sandbox)
    set_object_offset(object_uuid, 40.0, -20.0)
    set_object_rescale_state(object_uuid, display_scale=1.75)

    with _build_client() as client:
        response = client.post(f"/images/objects/{object_uuid}/reset-transform")

    assert response.status_code == 200
    body = response.json()
    assert body["offset_x"] == 0.0
    assert body["offset_y"] == 0.0
    assert body["display_scale"] == 1.0
    assert body["name"] == "Chair"

    metadata = get_object_by_uuid(object_uuid)
    assert metadata is not None
    assert metadata.offset_x == 0.0
    assert metadata.offset_y == 0.0
    assert metadata.display_scale == 1.0


def test_reset_transform_missing_uuid_returns_404(storage_sandbox: Path) -> None:
    with _build_client() as client:
        response = client.post("/images/objects/does-not-exist/reset-transform")
    assert response.status_code == 404
