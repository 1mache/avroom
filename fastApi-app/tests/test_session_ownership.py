"""Behavioral tests for the session-ownership guard (core/auth/ownership.py).

Every test authenticates as the default local user (AUTH_MODE=single_user,
the only mode active here) and probes a session/object owned by someone
else. All must 404 -- never 403, never a 200/500 -- with the same detail an
unknown uid would produce, so a caller can never learn "exists but isn't
mine" from "doesn't exist at all".
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

import settings  # noqa: E402
from core.object_metadata import create_object_metadata, save_object_metadata  # noqa: E402
from core.repositories import session_repo  # noqa: E402


@pytest.fixture
def storage_sandbox(monkeypatch: pytest.MonkeyPatch) -> Path:
    root = Path(tempfile.mkdtemp(prefix="avroom_ownership_test_"))
    images_dir = root / "images"
    glb_dir = root / "3d"
    images_dir.mkdir(parents=True, exist_ok=True)
    glb_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(images_dir))
    monkeypatch.setattr("api.routes.get_3d_storage_dir", lambda: glb_dir)
    monkeypatch.setattr("api.object_views.get_3d_storage_dir", lambda: glb_dir)
    assert settings.get_image_storage_dir() == images_dir
    return images_dir


def _client() -> Any:
    from fastapi.testclient import TestClient
    from main import app

    return TestClient(app)


def _seed_object_for(session_id: str, *, object_id: int = 0) -> str:
    """Persist a minimal object row under *session_id* (already registered
    elsewhere) and return its uuid. Does not touch the owning session row --
    `save_object_metadata`'s `register_uid` is a no-op once the row exists."""
    meta = create_object_metadata(
        session_id=session_id, object_id=object_id, average_depth=100.0, content_hash="abc123"
    )
    save_object_metadata(meta)
    return meta.uuid


# ---------------------------------------------------------------------------
# Path-{uid} routes
# ---------------------------------------------------------------------------

_NOT_FOUND_DETAIL = "Session not found for uid='{uid}'"


def _path_uid_cases(uid: str) -> list[tuple[str, str, dict[str, Any]]]:
    """(method, path, kwargs) for every path-{uid} route."""
    return [
        ("POST", f"/images/{uid}/batch", {"json": {"source": {"kind": "objects", "uuids": ["x"]}}}),
        ("DELETE", f"/images/{uid}", {}),
        ("POST", f"/images/{uid}/name", {"json": {"name": "Test"}}),
        ("POST", f"/images/{uid}/copy", {}),
        ("POST", f"/images/{uid}/history/undo", {}),
        ("POST", f"/images/{uid}/history/redo", {}),
        ("POST", f"/images/{uid}/sync-check", {"json": {"client_last_changed": None}}),
        ("POST", f"/images/{uid}/warm-maps", {}),
        (
            "POST",
            f"/images/{uid}/objects/import",
            {"files": {"file": ("cutout.png", b"fake-png-bytes", "image/png")}},
        ),
        ("GET", f"/images/{uid}/objects", {}),
        ("GET", f"/images/{uid}/cache", {}),
        ("GET", f"/images/{uid}/background", {}),
        ("GET", f"/images/{uid}/cutout", {}),
        ("GET", f"/images/{uid}/original", {}),
        ("GET", f"/images/{uid}/preview", {}),
        ("POST", f"/images/{uid}/preview", {"json": {"image_b64": "AAAA"}}),
        ("GET", f"/3d/{uid}/0", {}),
        ("GET", f"/3d/{uid}", {}),
    ]


_PATH_UID_CASE_COUNT = len(_path_uid_cases("x"))


@pytest.mark.parametrize("index", range(_PATH_UID_CASE_COUNT))
def test_path_uid_route_404s_for_other_users_session(
    storage_sandbox: Path, other_users_session: str, index: int
) -> None:
    method, path, kwargs = _path_uid_cases(other_users_session)[index]
    response = _client().request(method, path, **kwargs)
    assert response.status_code == 404, f"{method} {path} -> {response.status_code} {response.text}"
    assert response.json()["detail"] == _NOT_FOUND_DETAIL.format(uid=other_users_session)


@pytest.mark.parametrize("index", range(_PATH_UID_CASE_COUNT))
def test_path_uid_route_404s_identically_for_unknown_uid(storage_sandbox: Path, index: int) -> None:
    unknown_uid = "totally-unknown-uid"
    method, path, kwargs = _path_uid_cases(unknown_uid)[index]
    response = _client().request(method, path, **kwargs)
    assert response.status_code == 404
    assert response.json()["detail"] == _NOT_FOUND_DETAIL.format(uid=unknown_uid)


def test_owned_session_still_reachable(storage_sandbox: Path) -> None:
    """Smoke check: the guard must not break normal, owned access."""
    session_repo.register_uid("sess-mine")
    response = _client().get("/images/sess-mine/cache")
    assert response.status_code == 200
    assert response.json()["uid"] == "sess-mine"


# ---------------------------------------------------------------------------
# JSON-body-uid routes
# ---------------------------------------------------------------------------


def _body_uid_cases(uid: str) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        ("POST", "/images/click", {"json": {"image_id": uid, "x": 0, "y": 0}}),
        ("POST", "/images/segment", {"json": {"image_id": uid, "x": 0, "y": 0}}),
        ("POST", "/images/inpaint", {"json": {"image_id": uid, "mask_id": "0"}}),
        ("POST", "/images/erase", {"json": {"image_id": uid, "mask_b64": "AAAA"}}),
        ("POST", "/3d/test-3d", {"json": {"uid": uid, "object_id": 0}}),
        (
            "POST",
            "/images/novel-view",
            {"json": {"uid": uid, "object_id": 0, "elevation_deg": 0.0, "azimuth_deg": 0.0}},
        ),
    ]


@pytest.mark.parametrize("index", range(6))
def test_json_body_uid_route_404s_for_other_users_session(
    storage_sandbox: Path, other_users_session: str, index: int
) -> None:
    method, path, kwargs = _body_uid_cases(other_users_session)[index]
    response = _client().request(method, path, **kwargs)
    assert response.status_code == 404, f"{method} {path} -> {response.status_code} {response.text}"
    assert response.json()["detail"] == _NOT_FOUND_DETAIL.format(uid=other_users_session)


def test_json_body_route_still_parses_its_own_model(storage_sandbox: Path) -> None:
    """Proves the router-level dependency reading `request.body()` doesn't
    break the route's own Pydantic body parsing (FastAPI caches the body)."""
    session_repo.register_uid("sess-mine")
    response = _client().post("/images/inpaint", json={"image_id": "sess-mine", "mask_id": "0"})
    # 202 (queued) proves the body was parsed and reached the handler --
    # a guard-shaped failure would be 404, a body-reuse bug would be 422.
    assert response.status_code == 202


def test_multipart_upload_unaffected_by_guard(storage_sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("api.routes.get_upload_validation_enabled", lambda: False)
    monkeypatch.setattr("api.routes.get_camera_calibration_enabled", lambda: False)
    monkeypatch.setattr("api.routes.get_normal_map_enabled", lambda: False)
    response = _client().post(
        "/images/upload", files={"file": ("room.png", b"fake-png-bytes", "image/png")}
    )
    assert response.status_code == 200
    assert response.json()["image_id"]


def test_multipart_batch_on_other_users_session_404s(
    storage_sandbox: Path, other_users_session: str
) -> None:
    """Resolved from the path param alone; the multipart body is never touched."""
    response = _client().post(
        f"/images/{other_users_session}/objects/import",
        files={"file": ("cutout.png", b"fake-png-bytes", "image/png")},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == _NOT_FOUND_DETAIL.format(uid=other_users_session)


# ---------------------------------------------------------------------------
# object_uuid routes
# ---------------------------------------------------------------------------

_OBJECT_NOT_FOUND_DETAIL = "Object not found for uuid='{object_uuid}'"


def _object_uuid_cases(object_uuid: str) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        ("GET", f"/images/objects/{object_uuid}", {}),
        ("PATCH", f"/images/objects/{object_uuid}", {"json": {}}),
        ("POST", f"/images/objects/{object_uuid}/reset-transform", {}),
        ("POST", f"/images/objects/{object_uuid}/duplicate", {}),
        ("DELETE", f"/images/objects/{object_uuid}", {}),
        ("DELETE", f"/images/objects/{object_uuid}/3d", {}),
        ("POST", f"/images/objects/{object_uuid}/rescale-by-depth", {"json": {"x": 0, "y": 0}}),
        ("POST", f"/images/objects/{object_uuid}/smart-paste", {"json": {"x": 0, "y": 0}}),
    ]


@pytest.mark.parametrize("index", range(8))
def test_object_uuid_route_404s_for_other_users_object(
    storage_sandbox: Path, other_users_session: str, index: int
) -> None:
    object_uuid = _seed_object_for(other_users_session)
    method, path, kwargs = _object_uuid_cases(object_uuid)[index]
    response = _client().request(method, path, **kwargs)
    assert response.status_code == 404, f"{method} {path} -> {response.status_code} {response.text}"
    assert response.json()["detail"] == _OBJECT_NOT_FOUND_DETAIL.format(object_uuid=object_uuid)


@pytest.mark.parametrize("index", range(8))
def test_object_uuid_route_404s_identically_for_unknown_uuid(storage_sandbox: Path, index: int) -> None:
    unknown_uuid = "totally-unknown-uuid"
    method, path, kwargs = _object_uuid_cases(unknown_uuid)[index]
    response = _client().request(method, path, **kwargs)
    assert response.status_code == 404
    assert response.json()["detail"] == _OBJECT_NOT_FOUND_DETAIL.format(object_uuid=unknown_uuid)


# ---------------------------------------------------------------------------
# Cross-user listing
# ---------------------------------------------------------------------------


def test_sessions_list_excludes_other_users_sessions(
    storage_sandbox: Path, other_users_session: str
) -> None:
    session_repo.register_uid("sess-mine")
    response = _client().get("/images/sessions")
    assert response.status_code == 200
    uids = {row["uid"] for row in response.json()}
    assert "sess-mine" in uids
    assert other_users_session not in uids


def test_unknown_uid_objects_list_404s(storage_sandbox: Path) -> None:
    """The behavior change this guard closes: an unregistered uid used to
    return 200 + an empty list (see the deleted TODO in object_views.py)."""
    response = _client().get("/images/totally-unknown-uid/objects")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Attach-point regression: router-only clients (bypassing main.py) must also
# be guarded, since several existing tests build FastAPI(); include_router(...).
# ---------------------------------------------------------------------------


def test_router_only_client_enforces_ownership(storage_sandbox: Path, other_users_session: str) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.routes import router  # warm-maps lives here, not api.sessions

    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post(f"/images/{other_users_session}/warm-maps")
    assert response.status_code == 404
    assert response.json()["detail"] == _NOT_FOUND_DETAIL.format(uid=other_users_session)
