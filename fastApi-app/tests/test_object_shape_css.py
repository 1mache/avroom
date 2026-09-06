"""Tests for is_3d / CSS transform metadata persistence and clone inheritance."""

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
from schemas.common import CutoutBounds  # noqa: E402
from core.object_metadata import (  # noqa: E402
    build_clone_metadata,
    create_object_metadata,
    get_object_by_uuid,
    save_object_metadata,
)
from core.object_storage import object_cutout_path  # noqa: E402
from core.repositories.session_repo import register_uid  # noqa: E402


@pytest.fixture
def storage_sandbox(monkeypatch: pytest.MonkeyPatch) -> Path:
    root = Path(tempfile.mkdtemp(prefix="avroom_shape_css_"))
    images_dir = root / "images"
    glb_dir = root / "3d"
    images_dir.mkdir(parents=True, exist_ok=True)
    glb_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(images_dir))
    monkeypatch.setattr("api.routes.get_3d_storage_dir", lambda: glb_dir)
    return images_dir


def _write_png(path: Path) -> None:
    image = np.zeros((8, 8, 4), dtype=np.uint8)
    image[:, :] = (10, 20, 30, 255)
    success, encoded = cv2.imencode(".png", image)
    assert success
    path.write_bytes(encoded.tobytes())


def _build_client() -> Any:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_create_and_patch_css_and_is_3d(storage_sandbox: Path) -> None:
    uid = "sess-shape"
    register_uid(uid)
    _write_png(object_cutout_path(storage_sandbox, uid, 0))
    meta = create_object_metadata(
        session_id=uid,
        object_id=0,
        average_depth=100.0,
        content_hash="h1",
        is_3d=False,
        css_rotate_x_deg=1.0,
        css_rotate_y_deg=2.0,
        css_rotate_z_deg=3.0,
        css_perspective_px=500.0,
    )
    save_object_metadata(meta)

    loaded = get_object_by_uuid(meta.uuid)
    assert loaded is not None
    assert loaded.is_3d is False
    assert loaded.css_rotate_x_deg == 1.0
    assert loaded.css_perspective_px == 500.0

    with _build_client() as client:
        response = client.patch(
            f"/images/objects/{meta.uuid}",
            json={
                "css_rotate_x_deg": 15.0,
                "css_rotate_y_deg": -25.0,
                "css_rotate_z_deg": 0.0,
                "css_perspective_px": 900.0,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["is_3d"] is False
    assert body["css_rotate_x_deg"] == 15.0
    assert body["css_rotate_y_deg"] == -25.0
    assert body["css_perspective_px"] == 900.0


def test_clone_inherits_is_3d_and_css(storage_sandbox: Path) -> None:
    uid = "sess-clone-shape"
    register_uid(uid)
    _write_png(object_cutout_path(storage_sandbox, uid, 0))
    source = create_object_metadata(
        session_id=uid,
        object_id=0,
        average_depth=90.0,
        content_hash="h2",
        name="Poster",
        is_3d=False,
        css_rotate_x_deg=8.0,
        css_rotate_y_deg=-12.0,
        css_rotate_z_deg=1.0,
        css_perspective_px=700.0,
    )
    save_object_metadata(source)

    clone = build_clone_metadata(
        source,
        1,
        CutoutBounds(left=0, top=0, right=8, bottom=8, natural_width=8, natural_height=8),
    )
    assert clone.is_3d is False
    assert clone.css_rotate_x_deg == 8.0
    assert clone.css_rotate_y_deg == -12.0
    assert clone.css_rotate_z_deg == 1.0
    assert clone.css_perspective_px == 700.0
