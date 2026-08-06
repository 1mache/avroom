from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest
from PIL import Image

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from core.content_validation import ContentValidationOutcome
from core.image_validation import ImageValidationError, ImageValidator
from core.image_validation.checks import (
    AlphaEmptyCheck,
    AnimatedFrameCheck,
    BlurCheck,
    ExposureCheck,
    FileSizeCheck,
    FormatMimeCheck,
    ResolutionCheck,
    UniformSceneCheck,
    build_validation_context,
)


def _make_sharp_room_png(width: int = 800, height: int = 600) -> bytes:
    """Synthetic image with enough detail to pass technical checks."""
    rng = np.random.default_rng(42)
    bgr = rng.integers(40, 200, size=(height, width, 3), dtype=np.uint8)
    # Add edges for Laplacian variance.
    cv2.rectangle(bgr, (50, 50), (width - 50, height - 50), (20, 180, 220), 8)
    cv2.line(bgr, (0, height // 2), (width, height // 2), (90, 90, 90), 3)
    ok, buffer = cv2.imencode(".png", bgr)
    assert ok and buffer is not None
    return buffer.tobytes()


def _make_blurry_png(width: int = 800, height: int = 600) -> bytes:
    bgr = np.full((height, width, 3), 128, dtype=np.uint8)
    blurred = cv2.GaussianBlur(bgr, (51, 51), 0)
    ok, buffer = cv2.imencode(".png", blurred)
    assert ok and buffer is not None
    return buffer.tobytes()


def _make_transparent_png(width: int = 800, height: int = 600) -> bytes:
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[0, 0, 3] = 255
    ok, buffer = cv2.imencode(".png", rgba)
    assert ok and buffer is not None
    return buffer.tobytes()


def _make_gif_two_frames(width: int = 64, height: int = 64) -> bytes:
    frames = [
        Image.new("RGB", (width, height), color=(255, 0, 0)),
        Image.new("RGB", (width, height), color=(0, 255, 0)),
    ]
    output = io.BytesIO()
    frames[0].save(output, format="GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
    return output.getvalue()


def test_file_size_check_rejects_too_small() -> None:
    result = FileSizeCheck().run_bytes(b"x")
    assert result.passed is False
    assert result.name == "file_size"


def test_format_mime_check_rejects_unknown_bytes() -> None:
    result = FormatMimeCheck().run_bytes(b"not-an-image", content_type=None)
    assert result.passed is False


def test_animated_frame_check_rejects_gif() -> None:
    gif_bytes = _make_gif_two_frames()
    ctx = build_validation_context(gif_bytes, filename="anim.gif", content_type="image/gif")
    result = AnimatedFrameCheck().run(ctx)
    assert result.passed is False


def test_resolution_check_rejects_too_small() -> None:
    png = _make_sharp_room_png(width=32, height=32)
    ctx = build_validation_context(png, filename="small.png", content_type="image/png")
    result = ResolutionCheck().run(ctx)
    assert result.passed is False


def test_alpha_empty_check_rejects_mostly_transparent() -> None:
    png = _make_transparent_png()
    ctx = build_validation_context(png, filename="empty.png", content_type="image/png")
    result = AlphaEmptyCheck().run(ctx)
    assert result.passed is False


def test_blur_check_rejects_blurry_image() -> None:
    png = _make_blurry_png()
    ctx = build_validation_context(png, filename="blur.png", content_type="image/png")
    result = BlurCheck().run(ctx)
    assert result.passed is False


def test_exposure_check_rejects_underexposed() -> None:
    bgr = np.zeros((400, 400, 3), dtype=np.uint8)
    ok, buffer = cv2.imencode(".png", bgr)
    assert ok and buffer is not None
    ctx = build_validation_context(buffer.tobytes(), filename="dark.png", content_type="image/png")
    result = ExposureCheck().run(ctx)
    assert result.passed is False


def test_uniform_scene_check_rejects_flat_image() -> None:
    bgr = np.full((400, 400, 3), 128, dtype=np.uint8)
    ok, buffer = cv2.imencode(".png", bgr)
    assert ok and buffer is not None
    ctx = build_validation_context(buffer.tobytes(), filename="flat.png", content_type="image/png")
    result = UniformSceneCheck().run(ctx)
    assert result.passed is False


def test_image_validator_passes_sharp_room_png() -> None:
    png = _make_sharp_room_png()
    results = ImageValidator().validate(png, filename="room.png", content_type="image/png")
    assert len(results) >= 8
    assert all(result.passed for result in results)


def test_image_validator_short_circuits_on_first_failure() -> None:
    with pytest.raises(ImageValidationError) as exc_info:
        ImageValidator().validate(b"tiny", filename="tiny.png", content_type="image/png")
    assert exc_info.value.failed_results[0].name == "file_size"


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("fastapi") is None,
    reason="fastapi not installed",
)
def test_upload_skips_validation_when_validate_false(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from main import app

    with patch("api.routes.get_image_storage_dir", return_value=tmp_path):
        with patch("api.routes.get_upload_validation_enabled", return_value=False):
            with patch("api.routes.register_uid") as register_mock:
                with patch("api.routes.touch_session", return_value="2026-01-01T00:00:00+00:00"):
                    test_client = TestClient(app)
                    response = test_client.post(
                        "/images/upload",
                        files={"file": ("blur.png", _make_blurry_png(), "image/png")},
                    )

    assert response.status_code == 200
    register_mock.assert_called_once()
    # Original upload plus its dashboard-preview thumbnail (write_upload_preview).
    assert len(list(tmp_path.glob("*"))) == 2


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("fastapi") is None,
    reason="fastapi not installed",
)
def test_upload_rejects_technical_failure_before_persist(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from main import app
    from settings import get_image_storage_dir

    with patch("api.routes.get_image_storage_dir", return_value=tmp_path):
        with patch("api.routes.register_uid") as register_mock:
            client = TestClient(app)
            response = client.post(
                "/images/upload",
                files={"file": ("blur.png", _make_blurry_png(), "image/png")},
            )

    assert response.status_code == 422
    register_mock.assert_not_called()
    assert list(tmp_path.glob("*")) == []


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("fastapi") is None,
    reason="fastapi not installed",
)
def test_upload_rejects_content_failure_before_persist(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from main import app

    invalid_content = ContentValidationOutcome(
        is_valid=False,
        checks={"scene_space_or_landscape": False},
        scores={"scene_positive_max": 0.01},
        messages=("Image does not appear to be a room or landscape space.",),
    )

    with patch("api.routes.get_image_storage_dir", return_value=tmp_path):
        with patch("api.routes.get_inference_client") as client_factory:
            client_factory.return_value.run_validate_content.return_value = invalid_content
            with patch("api.routes.register_uid") as register_mock:
                test_client = TestClient(app)
                response = test_client.post(
                    "/images/upload",
                    files={"file": ("room.png", _make_sharp_room_png(), "image/png")},
                )

    assert response.status_code == 422
    register_mock.assert_not_called()
    assert list(tmp_path.glob("*")) == []


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("fastapi") is None,
    reason="fastapi not installed",
)
def test_upload_success_persists_file(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from main import app

    valid_content = ContentValidationOutcome(
        is_valid=True,
        checks={"scene_space_or_landscape": True},
        scores={"scene_positive_max": 0.9},
        messages=(),
    )

    with patch("api.routes.get_image_storage_dir", return_value=tmp_path):
        with patch("api.routes.get_inference_client") as client_factory:
            client_factory.return_value.run_validate_content.return_value = valid_content
            with patch("api.routes.register_uid") as register_mock:
                with patch("api.routes.touch_session", return_value="2026-01-01T00:00:00+00:00"):
                    test_client = TestClient(app)
                    response = test_client.post(
                        "/images/upload",
                        files={"file": ("room.png", _make_sharp_room_png(), "image/png")},
                    )

    assert response.status_code == 200
    register_mock.assert_called_once()
    # Original upload plus its dashboard-preview thumbnail (write_upload_preview).
    assert len(list(tmp_path.glob("*"))) == 2
    assert "image_id" in response.json()
