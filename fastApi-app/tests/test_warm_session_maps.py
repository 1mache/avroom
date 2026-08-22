from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

import settings  # noqa: E402
from core.depth_cache import content_hash_for_bytes, load_depth_map  # noqa: E402
from core.normal_cache import load_normal_map  # noqa: E402
from core.session_maps import WarmSessionMapsResult, warm_session_maps  # noqa: E402


def _png_bytes(width: int = 64, height: int = 48) -> bytes:
    bgr = np.full((height, width, 3), 100, dtype=np.uint8)
    cv2.rectangle(bgr, (5, 5), (width - 5, height - 5), (40, 160, 200), 2)
    ok, buffer = cv2.imencode(".png", bgr)
    assert ok and buffer is not None
    return buffer.tobytes()


def _fake_depth(_bgr: np.ndarray) -> np.ndarray:
    return np.full((_bgr.shape[0], _bgr.shape[1]), 128, dtype=np.uint8)


def _fake_normals_for_bytes(image_bytes: bytes) -> np.ndarray:
    decoded = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None
    h, w = decoded.shape[:2]
    normals = np.zeros((h, w, 3), dtype=np.float32)
    normals[:, :, 2] = 1.0
    return normals


@pytest.fixture
def storage_sandbox(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(images_dir))
    return images_dir


def test_warm_session_maps_writes_depth_and_normal_caches(
    storage_sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uid = "sess-warm"
    image_bytes = _png_bytes()
    (storage_sandbox / f"{uid}.png").write_bytes(image_bytes)
    settings.register_uid(uid)
    monkeypatch.setattr(settings, "get_normal_map_enabled", lambda: True)

    fake_segmentor = MagicMock()
    fake_segmentor.return_value.depth.map_depth = _fake_depth

    with patch("core.session_maps.load_avroom_attr", return_value=fake_segmentor):
        first = warm_session_maps(
            storage_sandbox,
            uid,
            map_normals_from_bytes=_fake_normals_for_bytes,
        )

    content_hash = content_hash_for_bytes(image_bytes)
    assert first.content_hash == content_hash
    assert first.depth_cache_hit is False
    assert first.normal_cache_hit is False
    assert load_depth_map(storage_sandbox, uid, content_hash) is not None
    assert load_normal_map(storage_sandbox, uid, content_hash) is not None

    with patch("core.session_maps.load_avroom_attr", return_value=fake_segmentor):
        second = warm_session_maps(
            storage_sandbox,
            uid,
            map_normals_from_bytes=_fake_normals_for_bytes,
        )

    assert second.depth_cache_hit is True
    assert second.normal_cache_hit is True


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("fastapi") is None,
    reason="fastapi not installed",
)
def test_warm_maps_endpoint_returns_cache_hits(storage_sandbox: Path) -> None:
    from fastapi.testclient import TestClient

    from main import app

    uid = "sess-api"
    (storage_sandbox / f"{uid}.png").write_bytes(_png_bytes())
    settings.register_uid(uid)

    client = MagicMock()
    client.run_warm_session_maps.return_value = WarmSessionMapsResult(
        session_id=uid,
        content_hash="abc123",
        depth_cache_hit=True,
        normal_cache_hit=True,
    )

    with patch("api.routes.get_image_storage_dir", return_value=storage_sandbox):
        with patch("api.routes.get_inference_client", return_value=client):
            response = TestClient(app).post(f"/images/{uid}/warm-maps")

    assert response.status_code == 200
    body = response.json()
    assert body["uid"] == uid
    assert body["content_hash"] == "abc123"
    assert body["depth_cache_hit"] is True
    assert body["normal_cache_hit"] is True
    client.run_warm_session_maps.assert_called_once()


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("fastapi") is None,
    reason="fastapi not installed",
)
def test_warm_maps_unknown_session_returns_404(storage_sandbox: Path) -> None:
    from fastapi.testclient import TestClient

    from main import app

    with patch("api.routes.get_image_storage_dir", return_value=storage_sandbox):
        response = TestClient(app).post("/images/missing/warm-maps")

    assert response.status_code == 404
