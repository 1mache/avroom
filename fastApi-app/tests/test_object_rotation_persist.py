"""Persist volumetric rotation PNG so it survives room re-entry."""

from __future__ import annotations

import base64
import sys
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

import settings  # noqa: E402
from core.object_metadata import (  # noqa: E402
    create_object_metadata,
    get_object_by_uuid,
    save_object_metadata,
)
from core.object_storage import object_cutout_path, object_rotated_path  # noqa: E402


@pytest.fixture
def storage_sandbox(monkeypatch: pytest.MonkeyPatch) -> Path:
    root = Path(tempfile.mkdtemp(prefix="avroom_rotation_persist_"))
    images_dir = root / "images"
    glb_dir = root / "3d"
    images_dir.mkdir(parents=True, exist_ok=True)
    glb_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(images_dir))
    monkeypatch.setattr("api.routes.get_3d_storage_dir", lambda: glb_dir)
    monkeypatch.setattr("api.object_views.get_3d_storage_dir", lambda: glb_dir)
    return images_dir


@pytest.fixture
def client(storage_sandbox: Path) -> Any:
    from api.object_views import router as views_router
    from api.routes import router as routes_router

    app = FastAPI()
    app.include_router(routes_router)
    app.include_router(views_router)
    return TestClient(app)


def _png_b64(rgba: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", rgba)
    assert ok
    return base64.b64encode(buf.tobytes()).decode("ascii")


def test_persist_rotation_survives_object_list(
    client: Any, storage_sandbox: Path
) -> None:
    uid = "rot-persist-uid"
    meta = create_object_metadata(
        session_id=uid,
        object_id=0,
        average_depth=100.0,
        content_hash="abc",
    )
    save_object_metadata(meta)
    cutout = np.zeros((40, 40, 4), dtype=np.uint8)
    cutout[10:30, 10:30] = (40, 80, 120, 255)
    object_cutout_path(storage_sandbox, uid, 0).write_bytes(
        cv2.imencode(".png", cutout)[1].tobytes()
    )

    rotated = np.zeros((40, 40, 4), dtype=np.uint8)
    rotated[5:35, 8:28] = (10, 200, 50, 255)
    payload = {
        "image_b64": _png_b64(rotated),
        "azimuth_deg": 25.0,
        "relative_elevation_deg": -10.0,
        "roll_deg": 15.0,
    }
    persist = client.post(f"/images/objects/{meta.uuid}/rotation", json=payload)
    assert persist.status_code == 200, persist.text

    loaded = get_object_by_uuid(meta.uuid)
    assert loaded is not None
    assert loaded.rotation_azimuth_deg == 25.0
    assert loaded.rotation_relative_elevation_deg == -10.0
    assert loaded.rotation_roll_deg == 15.0
    assert object_rotated_path(storage_sandbox, uid, 0).exists()

    listing = client.get(f"/images/{uid}/objects")
    assert listing.status_code == 200
    body = listing.json()
    assert len(body["objects"]) == 1
    obj = body["objects"][0]
    assert obj["rotation_azimuth_deg"] == 25.0
    assert obj["rotation_roll_deg"] == 15.0
    assert obj["rotated_b64"]
    assert obj["rotated_bounds"] is not None

    reset = client.post(f"/images/objects/{meta.uuid}/reset-transform")
    assert reset.status_code == 200
    cleared = get_object_by_uuid(meta.uuid)
    assert cleared is not None
    assert cleared.rotation_azimuth_deg is None
    assert not object_rotated_path(storage_sandbox, uid, 0).exists()
