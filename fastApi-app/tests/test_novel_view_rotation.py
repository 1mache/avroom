"""Tests for the /images/novel-view endpoint."""

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
from core.repositories import session_repo  # noqa: E402


class _FakeInferenceClient:
    """Stands in for the real inference pool client -- no GPU/model loading."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.generate_3d_calls: list[Path] = []
        self.glb_bytes: bytes = b"fake-glb-bytes"

    def run_generate_3d(self, *, cutout_path: Path) -> bytes:
        self.generate_3d_calls.append(cutout_path)
        return self.glb_bytes

    def run_novel_view(
        self,
        *,
        cutout_path: Path,
        elevation_deg: float,
        azimuth_deg: float,
        relative_elevation_deg: float,
        radius: float,
        mesh_path: Path,
    ) -> np.ndarray:
        self.calls.append(
            {
                "cutout_path": cutout_path,
                "elevation_deg": elevation_deg,
                "azimuth_deg": azimuth_deg,
                "relative_elevation_deg": relative_elevation_deg,
                "radius": radius,
                "mesh_path": mesh_path,
            }
        )
        # 4x4 fully-opaque BGRA image is enough to round-trip through
        # cutout-bounds extraction and PNG encode/decode.
        image = np.zeros((4, 4, 4), dtype=np.uint8)
        image[:, :, 3] = 255
        return image


@pytest.fixture
def storage_sandbox(monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect image + 3D storage to an isolated directory with one cutout."""
    root = Path(tempfile.mkdtemp(prefix="avroom_novel_view_test_"))
    images_dir = root / "images"
    glb_dir = root / "3d"
    images_dir.mkdir(parents=True, exist_ok=True)
    glb_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(images_dir))
    # The GLB cache-or-generate helper lives in core/object_3d.py (shared with
    # core/jobs/handlers.py's generate_3d job), not api/novel_view.py anymore
    # -- patch its own get_3d_storage_dir reference.
    monkeypatch.setattr("core.object_3d.get_3d_storage_dir", lambda: glb_dir)
    assert settings.get_image_storage_dir() == images_dir
    session_repo.register_uid("sess-1")

    cutout = np.zeros((4, 4, 4), dtype=np.uint8)
    cutout[:, :, 3] = 255
    success, encoded = cv2.imencode(".png", cutout)
    assert success
    (images_dir / "sess-1_0_cutout.png").write_bytes(encoded.tobytes())

    # Pre-seed a GLB so existing tests exercise mesh_path without generating 3D.
    (glb_dir / "sess-1_0.glb").write_bytes(b"cached-glb")

    return images_dir


@pytest.fixture
def glb_dir(storage_sandbox: Path) -> Path:
    """Sibling 3D storage dir created by ``storage_sandbox``."""

    return storage_sandbox.parent / "3d"

@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> _FakeInferenceClient:
    client = _FakeInferenceClient()
    # run_novel_view on every call goes through api/novel_view.py's own
    # get_inference_client reference -- there is no cache module anymore, the
    # route calls the inference client directly.
    monkeypatch.setattr("api.novel_view.get_inference_client", lambda: client)
    # run_generate_3d on a cache miss goes through core/object_3d.py's own
    # get_inference_client reference (shared with core/jobs/handlers.py's
    # generate_3d job), not api.novel_view's -- patch that one too.
    monkeypatch.setattr("core.object_3d.get_inference_client", lambda: client)
    return client


def _build_client() -> Any:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.novel_view import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _post_novel_view(client: Any, **overrides: Any) -> Any:
    payload = {
        "uid": "sess-1",
        "object_id": 0,
        "elevation_deg": 0.0,
        "azimuth_deg": 0.0,
    }
    payload.update(overrides)
    return client.post("/images/novel-view", json=payload)


def test_response_echoes_exact_azimuth(
    storage_sandbox: Path, fake_client: _FakeInferenceClient, glb_dir: Path
) -> None:
    with _build_client() as client:
        response = _post_novel_view(client, azimuth_deg=37.0)

    assert response.status_code == 200
    body = response.json()
    assert body["azimuth_deg"] == 37.0
    assert fake_client.calls[0]["azimuth_deg"] == 37.0
    assert fake_client.calls[0]["mesh_path"] == glb_dir / "sess-1_0.glb"
    assert not fake_client.generate_3d_calls
    # No per-angle PNG is ever written to disk anymore -- every call renders
    # fresh from the GLB.
    assert not list(storage_sandbox.glob("*_novel_az*"))


def test_repeat_request_calls_model_again(
    storage_sandbox: Path, fake_client: _FakeInferenceClient
) -> None:
    with _build_client() as client:
        first = _post_novel_view(client, azimuth_deg=40.0)
        second = _post_novel_view(client, azimuth_deg=40.0)

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(fake_client.calls) == 2, "there is no cache -- every request renders fresh"


def test_glb_cache_miss_generates_and_writes(
    storage_sandbox: Path, fake_client: _FakeInferenceClient, glb_dir: Path
) -> None:
    missing_cutout = storage_sandbox / "sess-1_1_cutout.png"
    cutout = np.zeros((4, 4, 4), dtype=np.uint8)
    cutout[:, :, 3] = 255
    success, encoded = cv2.imencode(".png", cutout)
    assert success
    missing_cutout.write_bytes(encoded.tobytes())

    with _build_client() as client:
        response = _post_novel_view(client, object_id=1, azimuth_deg=20.0)

    assert response.status_code == 200
    assert len(fake_client.generate_3d_calls) == 1
    written = glb_dir / "sess-1_1.glb"
    assert written.exists()
    assert written.read_bytes() == b"fake-glb-bytes"
    assert fake_client.calls[0]["mesh_path"] == written
    assert fake_client.calls[0]["azimuth_deg"] == 20.0


def test_invalid_pose_returns_422(storage_sandbox: Path, fake_client: _FakeInferenceClient) -> None:
    with _build_client() as client:
        response = _post_novel_view(
            client, azimuth_deg=-15.0, azimuth_direction="CLOCKWISE"
        )

    assert response.status_code == 422
    assert not fake_client.calls


def test_missing_cutout_returns_404(
    storage_sandbox: Path, fake_client: _FakeInferenceClient
) -> None:
    with _build_client() as client:
        response = _post_novel_view(client, object_id=99)

    assert response.status_code == 404
    assert not fake_client.calls
