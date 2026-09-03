"""Tests for the is_admin gate (core/auth/admin.py): the /debug router and
the upload endpoint's skip_validation flag must both 403 for a non-admin and
succeed for an admin. Runs under AUTH_MODE=single_user (the default) --
the fixed local user's is_admin flag is flipped directly in the DB to cover
both cases, mirroring how core/auth/single_user.py provisions it.
"""

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


@pytest.fixture(autouse=True)
def _single_user_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force AUTH_MODE=single_user regardless of a dev machine's own .env --
    these tests exercise the fixed local user, not real accounts (see
    test_auth_jwt.py's `jwt_mode` fixture for the mirror-image case)."""
    monkeypatch.setenv("AUTH_MODE", "single_user")


def _png_bytes(width: int = 64, height: int = 48) -> bytes:
    bgr = np.full((height, width, 3), 100, dtype=np.uint8)
    ok, buffer = cv2.imencode(".png", bgr)
    assert ok and buffer is not None
    return buffer.tobytes()


def _set_local_user_admin(value: bool) -> None:
    from core.auth.single_user import get_or_create_default_user
    from db.session import session_scope

    with session_scope() as db:
        user = get_or_create_default_user(db)
        user.is_admin = value


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("fastapi") is None,
    reason="fastapi not installed",
)
def test_debug_endpoint_403_for_non_admin() -> None:
    from fastapi.testclient import TestClient

    from main import app

    _set_local_user_admin(False)
    response = TestClient(app).post(
        "/debug/validate", files={"file": ("room.png", _png_bytes(), "image/png")}
    )
    assert response.status_code == 403


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("fastapi") is None,
    reason="fastapi not installed",
)
def test_debug_endpoint_ok_for_admin() -> None:
    from fastapi.testclient import TestClient

    from main import app

    _set_local_user_admin(True)
    response = TestClient(app).post(
        "/debug/validate", files={"file": ("room.png", _png_bytes(), "image/png")}
    )
    assert response.status_code == 200


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("fastapi") is None,
    reason="fastapi not installed",
)
def test_upload_skip_validation_403_for_non_admin(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from main import app

    _set_local_user_admin(False)
    with patch("api.routes.get_image_storage_dir", return_value=tmp_path):
        response = TestClient(app).post(
            "/images/upload",
            files={"file": ("room.png", _png_bytes(), "image/png")},
            data={"skip_validation": "true"},
        )
    assert response.status_code == 403


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("fastapi") is None,
    reason="fastapi not installed",
)
def test_upload_skip_validation_bypasses_validation_for_admin(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from main import app

    _set_local_user_admin(True)
    validator = MagicMock()
    validator.validate.side_effect = AssertionError("validation should have been skipped")
    with patch("api.routes.get_image_storage_dir", return_value=tmp_path):
        with patch("api.routes.get_upload_validation_enabled", return_value=True):
            with patch("api.routes.ImageValidator", return_value=validator):
                with patch("api.routes.get_camera_calibration_enabled", return_value=False):
                    with patch("api.routes.get_normal_map_enabled", return_value=False):
                        response = TestClient(app).post(
                            "/images/upload",
                            files={"file": ("room.png", _png_bytes(), "image/png")},
                            data={"skip_validation": "true"},
                        )
    assert response.status_code == 200
    validator.validate.assert_not_called()


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("fastapi") is None,
    reason="fastapi not installed",
)
def test_auth_me_reports_is_admin() -> None:
    from fastapi.testclient import TestClient

    from main import app

    _set_local_user_admin(True)
    response = TestClient(app).get("/auth/me")
    assert response.status_code == 200
    assert response.json()["is_admin"] is True

    _set_local_user_admin(False)
    response = TestClient(app).get("/auth/me")
    assert response.status_code == 200
    assert response.json()["is_admin"] is False
