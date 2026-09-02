"""Tests for POST /images/{uid}/objects/import."""

from __future__ import annotations

import io
import sys
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest
from PIL import Image

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

import settings  # noqa: E402
from core.object_metadata import get_object_by_uuid, list_object_ids  # noqa: E402
from core.object_storage import current_background_path, object_cutout_path  # noqa: E402
from core.repositories import session_repo  # noqa: E402


@pytest.fixture
def storage_sandbox(monkeypatch: pytest.MonkeyPatch) -> Path:
    root = Path(tempfile.mkdtemp(prefix="avroom_object_import_"))
    images_dir = root / "images"
    glb_dir = root / "3d"
    images_dir.mkdir(parents=True, exist_ok=True)
    glb_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(images_dir))
    monkeypatch.setattr("api.routes.get_3d_storage_dir", lambda: glb_dir)
    assert settings.get_image_storage_dir() == images_dir
    return images_dir


def _canvas_png(width: int, height: int) -> bytes:
    bgr = np.full((height, width, 3), 120, dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", bgr)
    assert ok
    return encoded.tobytes()


def _cutout_png(width: int, height: int) -> bytes:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    image.paste((200, 100, 50, 255), (2, 2, width - 2, height - 2))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _seed_session(images_dir: Path, *, uid: str = "sess-1", canvas: tuple[int, int] = (80, 60)) -> None:
    session_repo.register_uid(uid)
    width, height = canvas
    (images_dir / f"{uid}.png").write_bytes(_canvas_png(width, height))
    current_background_path(images_dir, uid).write_bytes(_canvas_png(width, height))


def _build_client() -> Any:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_import_object_persists_cutout_without_touching_background(storage_sandbox: Path) -> None:
    _seed_session(storage_sandbox)
    background_before = current_background_path(storage_sandbox, "sess-1").read_bytes()
    cutout_bytes = _cutout_png(20, 16)

    with _build_client() as client:
        response = client.post(
            "/images/sess-1/objects/import",
            files={"file": ("chair.png", cutout_bytes, "image/png")},
        )

    assert response.status_code == 201
    object_uuid = response.json()["object_uuid"]
    metadata = get_object_by_uuid(object_uuid)
    assert metadata is not None
    assert metadata.session_id == "sess-1"
    assert metadata.object_id == 0
    assert list_object_ids("sess-1") == [0]

    cutout_path = object_cutout_path(storage_sandbox, "sess-1", 0)
    assert cutout_path.exists()
    assert cutout_path.read_bytes() != cutout_bytes
    assert current_background_path(storage_sandbox, "sess-1").read_bytes() == background_before


def test_import_rejects_missing_session(storage_sandbox: Path) -> None:
    with _build_client() as client:
        response = client.post(
            "/images/missing-session/objects/import",
            files={"file": ("chair.png", _cutout_png(10, 10), "image/png")},
        )
    assert response.status_code == 404


def test_import_rejects_empty_alpha(storage_sandbox: Path) -> None:
    _seed_session(storage_sandbox)
    image = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    empty = buffer.getvalue()

    with _build_client() as client:
        response = client.post(
            "/images/sess-1/objects/import",
            files={"file": ("empty.png", empty, "image/png")},
        )
    assert response.status_code == 422


def _full_frame_cutout_png(
    frame_width: int,
    frame_height: int,
    *,
    object_box: tuple[int, int, int, int],
) -> bytes:
    """Build a canvas-sized PNG with a small opaque object embedded in it."""
    image = Image.new("RGBA", (frame_width, frame_height), (0, 0, 0, 0))
    image.paste((200, 100, 50, 255), object_box)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_import_accepts_full_frame_cutout_larger_than_canvas(storage_sandbox: Path) -> None:
    _seed_session(storage_sandbox, canvas=(40, 40))
    # Full-frame export from a bigger room photo; visible object is tiny.
    cutout_bytes = _full_frame_cutout_png(500, 400, object_box=(230, 180, 270, 220))

    with _build_client() as client:
        response = client.post(
            "/images/sess-1/objects/import",
            files={"file": ("chair.png", cutout_bytes, "image/png")},
        )

    assert response.status_code == 201


def test_import_scales_down_object_larger_than_canvas(storage_sandbox: Path) -> None:
    _seed_session(storage_sandbox, canvas=(40, 40))
    oversized = _cutout_png(50, 50)

    with _build_client() as client:
        response = client.post(
            "/images/sess-1/objects/import",
            files={"file": ("big.png", oversized, "image/png")},
        )

    assert response.status_code == 201
    cutout_path = object_cutout_path(storage_sandbox, "sess-1", 0)
    with Image.open(cutout_path) as imported:
        assert imported.size == (40, 40)
