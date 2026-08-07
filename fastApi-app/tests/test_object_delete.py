"""Tests for DELETE /images/objects/{uuid}."""

from __future__ import annotations

import json
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
    list_object_ids,
    object_cutout_path,
    object_glb_path,
    object_novel_view_path,
    object_novel_view_preview_path,
)


@pytest.fixture
def storage_sandbox(monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect image + 3D storage and sidecars to an isolated directory."""

    root = Path(tempfile.mkdtemp(prefix="avroom_object_delete_"))
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
    with_novel: bool = True,
    content_hash: str = "abc123",
) -> str:
    """Create cutout (+ optional GLB/novel views) and metadata; return object uuid."""

    cutout_bytes = _write_png(object_cutout_path(images_dir, uid, object_id))
    if with_glb:
        object_glb_path(glb_dir, uid, object_id).write_bytes(b"fake-glb")
    if with_novel:
        novel = object_novel_view_path(images_dir, uid, object_id, 40.0, 0.0)
        novel.write_bytes(b"novel-bytes")
        preview = object_novel_view_preview_path(images_dir, uid, object_id, 40.0, 0.0)
        preview.write_bytes(b"preview-bytes")

    meta = create_object_metadata(
        session_id=uid,
        object_id=object_id,
        average_depth=120.5,
        content_hash=content_hash,
        source_elevation_deg=18.0,
        name=name,
    )
    save_object_metadata(images_dir, meta)
    assert cutout_bytes
    return meta.uuid


def _build_client() -> Any:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_delete_removes_all_artifacts_and_index_entry(
    storage_sandbox: Path, glb_dir: Path
) -> None:
    settings.register_uid("sess-1")
    before = settings.touch_session("sess-1")
    object_uuid = _seed_object(storage_sandbox, glb_dir, object_id=0)

    with _build_client() as client:
        response = client.delete(f"/images/objects/{object_uuid}")

    assert response.status_code == 204
    assert not object_cutout_path(storage_sandbox, "sess-1", 0).exists()
    assert not object_glb_path(glb_dir, "sess-1", 0).exists()
    assert not object_novel_view_path(storage_sandbox, "sess-1", 0, 40.0, 0.0).exists()
    assert not object_novel_view_preview_path(storage_sandbox, "sess-1", 0, 40.0, 0.0).exists()
    assert not (storage_sandbox / "sess-1_0_meta.json").exists()
    assert get_object_by_uuid(storage_sandbox, object_uuid) is None

    index_path = settings.get_image_storage_dir().parent / "object_index.json"
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        assert object_uuid not in index

    after = settings.get_session_last_changed("sess-1")
    assert after is not None
    assert after >= before


def test_delete_without_optional_artifacts(storage_sandbox: Path, glb_dir: Path) -> None:
    object_uuid = _seed_object(
        storage_sandbox, glb_dir, with_glb=False, with_novel=False
    )

    with _build_client() as client:
        response = client.delete(f"/images/objects/{object_uuid}")

    assert response.status_code == 204
    assert not object_cutout_path(storage_sandbox, "sess-1", 0).exists()


def test_missing_uuid_returns_404(storage_sandbox: Path) -> None:
    with _build_client() as client:
        response = client.delete("/images/objects/does-not-exist")
    assert response.status_code == 404


def test_double_delete_second_call_returns_404(storage_sandbox: Path, glb_dir: Path) -> None:
    object_uuid = _seed_object(storage_sandbox, glb_dir)

    with _build_client() as client:
        first = client.delete(f"/images/objects/{object_uuid}")
        second = client.delete(f"/images/objects/{object_uuid}")

    assert first.status_code == 204
    assert second.status_code == 404


def test_legacy_object_zero_cleans_up_unnumbered_files(
    storage_sandbox: Path, glb_dir: Path
) -> None:
    object_uuid = _seed_object(storage_sandbox, glb_dir, object_id=0)
    # Simulate a pre-numbering session: legacy unnumbered cutout/glb alongside
    # the numbered ones written by _seed_object.
    legacy_cutout = storage_sandbox / "sess-1_cutout.png"
    legacy_cutout.write_bytes(_write_png(legacy_cutout))
    legacy_glb = glb_dir / "sess-1.glb"
    legacy_glb.write_bytes(b"legacy-glb")

    with _build_client() as client:
        response = client.delete(f"/images/objects/{object_uuid}")

    assert response.status_code == 204
    assert not legacy_cutout.exists()
    assert not legacy_glb.exists()
    assert list_object_ids(storage_sandbox, "sess-1") == []


def test_background_depth_and_preview_survive(storage_sandbox: Path, glb_dir: Path) -> None:
    bg = storage_sandbox / "sess-1_background.png"
    bg.write_bytes(b"background-bytes")
    depth_path = storage_sandbox / "sess-1_depth_depth-hash.npy"
    np.save(depth_path, np.zeros((2, 2), dtype=np.uint8))
    preview_path = storage_sandbox / "sess-1_preview.jpg"
    preview_path.write_bytes(b"preview-jpeg-bytes")

    object_uuid = _seed_object(storage_sandbox, glb_dir, content_hash="depth-hash")

    with _build_client() as client:
        response = client.delete(f"/images/objects/{object_uuid}")

    assert response.status_code == 204
    assert bg.read_bytes() == b"background-bytes"
    assert depth_path.exists()
    assert preview_path.read_bytes() == b"preview-jpeg-bytes"


def test_second_object_untouched_by_deleting_first(
    storage_sandbox: Path, glb_dir: Path
) -> None:
    first_uuid = _seed_object(storage_sandbox, glb_dir, object_id=0, name="Chair")
    second_uuid = _seed_object(
        storage_sandbox, glb_dir, object_id=1, name="Sofa", content_hash="hash-2"
    )

    with _build_client() as client:
        response = client.delete(f"/images/objects/{first_uuid}")

    assert response.status_code == 204
    assert object_cutout_path(storage_sandbox, "sess-1", 1).exists()
    remaining = get_object_by_uuid(storage_sandbox, second_uuid)
    assert remaining is not None
    assert remaining.name == "Sofa"
    assert list_object_ids(storage_sandbox, "sess-1") == [1]
