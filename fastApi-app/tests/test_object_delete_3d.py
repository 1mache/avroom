"""Tests for DELETE /images/objects/{uuid}/3d."""

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
from core.object_storage import (  # noqa: E402
    object_cutout_path,
    object_glb_path,
)


@pytest.fixture
def storage_sandbox(monkeypatch: pytest.MonkeyPatch) -> Path:
    root = Path(tempfile.mkdtemp(prefix="avroom_object_delete_3d_"))
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


def _write_png(path: Path) -> None:
    image = np.zeros((4, 4, 4), dtype=np.uint8)
    image[:, :] = (10, 20, 30, 255)
    success, encoded = cv2.imencode(".png", image)
    assert success
    path.write_bytes(encoded.tobytes())


def _seed_object(
    images_dir: Path,
    glb_dir: Path,
    *,
    uid: str = "sess-1",
    object_id: int = 0,
    with_glb: bool = True,
) -> str:
    _write_png(object_cutout_path(images_dir, uid, object_id))
    if with_glb:
        object_glb_path(glb_dir, uid, object_id).write_bytes(b"fake-glb")

    meta = create_object_metadata(
        session_id=uid,
        object_id=object_id,
        average_depth=100.0,
        content_hash="abc123",
    )
    save_object_metadata(meta)
    return meta.uuid


@pytest.fixture
def client(storage_sandbox: Path) -> Any:
    from api.routes import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_delete_3d_removes_only_target_glb(
    client: Any, storage_sandbox: Path, glb_dir: Path
) -> None:
    source_uuid = _seed_object(storage_sandbox, glb_dir, object_id=0, with_glb=True)
    clone_meta = create_object_metadata(
        session_id="sess-1",
        object_id=1,
        average_depth=100.0,
        content_hash="abc123",
        clone_root_uuid=source_uuid,
        clone_root_label="Object 0",
        clone_index=0,
    )
    save_object_metadata(clone_meta)
    _write_png(object_cutout_path(storage_sandbox, "sess-1", 1))
    object_glb_path(glb_dir, "sess-1", 1).write_bytes(b"clone-glb")

    response = client.delete(f"/images/objects/{clone_meta.uuid}/3d")
    assert response.status_code == 204

    assert not object_glb_path(glb_dir, "sess-1", 1).exists()
    assert object_glb_path(glb_dir, "sess-1", 0).exists()
    assert get_object_by_uuid(clone_meta.uuid) is not None


def test_delete_3d_unknown_object_returns_404(client: Any) -> None:
    response = client.delete("/images/objects/does-not-exist/3d")
    assert response.status_code == 404


def test_delete_3d_no_glb_returns_404(
    client: Any, storage_sandbox: Path, glb_dir: Path
) -> None:
    object_uuid = _seed_object(storage_sandbox, glb_dir, with_glb=False)
    response = client.delete(f"/images/objects/{object_uuid}/3d")
    assert response.status_code == 404
