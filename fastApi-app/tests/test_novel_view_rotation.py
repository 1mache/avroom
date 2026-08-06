"""Tests for the /images/novel-view endpoint's HTTP-layer pose snapping and cache."""

from __future__ import annotations

import base64
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

import settings  # noqa: E402
from api.novel_view import _normalize_azimuth_deg, _snap_to_step  # noqa: E402


class TestSnapHelpers:
    def test_snaps_to_nearest_10(self) -> None:
        assert _snap_to_step(37.0, 10.0) == 40.0
        assert _snap_to_step(33.0, 10.0) == 30.0
        assert _snap_to_step(-7.0, 10.0) == -10.0

    def test_snap_returns_positive_zero(self) -> None:
        result = _snap_to_step(-2.0, 10.0)
        assert result == 0.0
        assert str(result) == "0.0"

    def test_normalize_wraps_into_range(self) -> None:
        assert _normalize_azimuth_deg(355.0) == -5.0
        assert _normalize_azimuth_deg(-355.0) == 5.0
        assert _normalize_azimuth_deg(180.0) == 180.0
        assert _normalize_azimuth_deg(-180.0) == 180.0

    def test_normalize_passthrough_within_range(self) -> None:
        assert _normalize_azimuth_deg(40.0) == 40.0
        assert _normalize_azimuth_deg(-170.0) == -170.0


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
    monkeypatch.setattr("api.novel_view.get_3d_storage_dir", lambda: glb_dir)
    assert settings.get_image_storage_dir() == images_dir

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
    monkeypatch.setattr("api.novel_view.get_inference_client", lambda: client)
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


def test_response_echoes_snapped_azimuth(
    storage_sandbox: Path, fake_client: _FakeInferenceClient, glb_dir: Path
) -> None:
    with _build_client() as client:
        response = _post_novel_view(client, azimuth_deg=37.0)

    assert response.status_code == 200
    body = response.json()
    assert body["azimuth_deg"] == 40.0
    assert fake_client.calls[0]["azimuth_deg"] == 40.0
    assert fake_client.calls[0]["mesh_path"] == glb_dir / "sess-1_0.glb"
    assert not fake_client.generate_3d_calls


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


def test_near_identical_poses_share_one_cache_entry(
    storage_sandbox: Path, fake_client: _FakeInferenceClient
) -> None:
    with _build_client() as client:
        first = _post_novel_view(client, azimuth_deg=36.0)
        second = _post_novel_view(client, azimuth_deg=44.0)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["azimuth_deg"] == second.json()["azimuth_deg"] == 40.0
    assert len(fake_client.calls) == 1, "second request should have been served from cache"

    cache_path = storage_sandbox / "sess-1_0_novel_az40_el0.png"
    assert cache_path.exists()


def test_stale_cache_after_cutout_rewrite_resynthesizes(
    storage_sandbox: Path, fake_client: _FakeInferenceClient
) -> None:
    with _build_client() as client:
        _post_novel_view(client, azimuth_deg=40.0)
        assert len(fake_client.calls) == 1

        # Simulate rescale-by-depth rewriting the cutout in place, strictly
        # after the cached rotation was written.
        time.sleep(0.05)
        cutout_path = storage_sandbox / "sess-1_0_cutout.png"
        cutout_path.write_bytes(cutout_path.read_bytes())

        _post_novel_view(client, azimuth_deg=40.0)

    assert len(fake_client.calls) == 2, "stale cache entry must not be served"


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


def _post_preview_cache(client: Any, **overrides: Any) -> Any:
    payload = {
        "uid": "sess-1",
        "object_id": 0,
        "azimuth_deg": 0.0,
        "image_b64": base64.b64encode(b"fake-preview-bytes").decode("ascii"),
    }
    payload.update(overrides)
    return client.post("/images/novel-view/preview-cache", json=payload)


class TestPreviewCache:
    def test_writes_preview_file_at_snapped_pose(self, storage_sandbox: Path) -> None:
        with _build_client() as client:
            response = _post_preview_cache(client, azimuth_deg=37.0)

        assert response.status_code == 204
        preview_path = storage_sandbox / "sess-1_0_novel_az40_el0.preview.png"
        assert preview_path.exists()
        assert preview_path.read_bytes() == b"fake-preview-bytes"

    def test_invalid_base64_returns_422(self, storage_sandbox: Path) -> None:
        with _build_client() as client:
            response = _post_preview_cache(client, image_b64="not-valid-base64!!!")

        assert response.status_code == 422

    def test_real_result_deletes_matching_preview(
        self, storage_sandbox: Path, fake_client: _FakeInferenceClient
    ) -> None:
        with _build_client() as client:
            cache_response = _post_preview_cache(client, azimuth_deg=37.0)
            assert cache_response.status_code == 204
            preview_path = storage_sandbox / "sess-1_0_novel_az40_el0.preview.png"
            assert preview_path.exists()

            real_response = _post_novel_view(client, azimuth_deg=37.0)

        assert real_response.status_code == 200
        assert not preview_path.exists()

    def test_cache_hit_also_deletes_matching_preview(
        self, storage_sandbox: Path, fake_client: _FakeInferenceClient
    ) -> None:
        with _build_client() as client:
            _post_novel_view(client, azimuth_deg=40.0)
            assert len(fake_client.calls) == 1

            preview_path = storage_sandbox / "sess-1_0_novel_az40_el0.preview.png"
            preview_path.write_bytes(b"leftover-preview")

            second = _post_novel_view(client, azimuth_deg=40.0)

        assert second.status_code == 200
        assert len(fake_client.calls) == 1, "second request should still be a cache hit"
        assert not preview_path.exists()

    def test_preview_untouched_when_synthesis_fails(
        self, storage_sandbox: Path, fake_client: _FakeInferenceClient
    ) -> None:
        def _boom(**_kwargs: Any) -> np.ndarray:
            raise RuntimeError("model exploded")

        fake_client.run_novel_view = _boom  # type: ignore[method-assign]

        with _build_client() as client:
            _post_preview_cache(client, azimuth_deg=37.0)
            preview_path = storage_sandbox / "sess-1_0_novel_az40_el0.preview.png"
            assert preview_path.exists()

            response = _post_novel_view(client, azimuth_deg=37.0)

        assert response.status_code == 500
        assert preview_path.exists(), "preview must survive a failed synthesis"
