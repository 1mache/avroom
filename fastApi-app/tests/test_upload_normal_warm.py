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

from core.depth_cache import content_hash_for_bytes  # noqa: E402
from core.normal_cache import load_normal_map  # noqa: E402


def _png_bytes(width: int = 64, height: int = 48) -> bytes:
    bgr = np.full((height, width, 3), 100, dtype=np.uint8)
    cv2.rectangle(bgr, (5, 5), (width - 5, height - 5), (40, 160, 200), 2)
    ok, buffer = cv2.imencode(".png", bgr)
    assert ok and buffer is not None
    return buffer.tobytes()


def _fake_normals_for_bytes(image_bytes: bytes) -> np.ndarray:
    decoded = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None
    h, w = decoded.shape[:2]
    normals = np.zeros((h, w, 3), dtype=np.float32)
    normals[:, :, 2] = 1.0
    return normals


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("fastapi") is None,
    reason="fastapi not installed",
)
def test_upload_warms_normal_cache(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from main import app

    image_bytes = _png_bytes()
    client = MagicMock()
    client.run_map_normals.side_effect = lambda image_bytes: _fake_normals_for_bytes(image_bytes)

    with patch("api.routes.get_image_storage_dir", return_value=tmp_path):
        with patch("api.routes.get_upload_validation_enabled", return_value=False):
            with patch("api.routes.get_camera_calibration_enabled", return_value=False):
                with patch("api.routes.get_normal_map_enabled", return_value=True):
                    with patch("api.routes.get_inference_client", return_value=client):
                        with patch("api.routes.register_uid"):
                            with patch(
                                "api.routes.touch_session",
                                return_value="2026-01-01T00:00:00+00:00",
                            ):
                                response = TestClient(app).post(
                                    "/images/upload",
                                    files={"file": ("room.png", image_bytes, "image/png")},
                                )

    assert response.status_code == 200
    image_id = response.json()["image_id"]
    client.run_map_normals.assert_called_once()
    content_hash = content_hash_for_bytes(image_bytes)
    loaded = load_normal_map(tmp_path, image_id, content_hash)
    assert loaded is not None
    assert loaded.shape[2] == 3


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("fastapi") is None,
    reason="fastapi not installed",
)
def test_upload_survives_normal_map_failure(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from main import app

    client = MagicMock()
    client.run_map_normals.side_effect = RuntimeError("Metric3D boom")

    with patch("api.routes.get_image_storage_dir", return_value=tmp_path):
        with patch("api.routes.get_upload_validation_enabled", return_value=False):
            with patch("api.routes.get_camera_calibration_enabled", return_value=False):
                with patch("api.routes.get_normal_map_enabled", return_value=True):
                    with patch("api.routes.get_inference_client", return_value=client):
                        with patch("api.routes.register_uid"):
                            with patch(
                                "api.routes.touch_session",
                                return_value="2026-01-01T00:00:00+00:00",
                            ):
                                response = TestClient(app).post(
                                    "/images/upload",
                                    files={"file": ("room.png", _png_bytes(), "image/png")},
                                )

    assert response.status_code == 200
    assert list(tmp_path.glob("*_normal_*.npy")) == []
