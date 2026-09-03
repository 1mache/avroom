"""Behavioral tests for the Project layer: `api/projects.py` + `core/repositories/project_repo.py`.

Every test authenticates as the default local user (AUTH_MODE=single_user).
Ownership tests mirror test_session_ownership.py's pattern: a caller-supplied
project_id belonging to someone else 404s exactly like an unknown one.
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
from core.repositories import project_repo, session_repo  # noqa: E402

_OTHER_USER_ID = "00000000-0000-0000-0000-000000000099"
_NOT_FOUND_DETAIL = "Project not found for id='{project_id}'"


@pytest.fixture
def storage_sandbox(monkeypatch: pytest.MonkeyPatch) -> Path:
    root = Path(tempfile.mkdtemp(prefix="avroom_projects_test_"))
    images_dir = root / "images"
    glb_dir = root / "3d"
    images_dir.mkdir(parents=True, exist_ok=True)
    glb_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "IMAGE_STORAGE_DIR", str(images_dir))
    monkeypatch.setattr("core.session_teardown.get_3d_storage_dir", lambda: glb_dir)
    assert settings.get_image_storage_dir() == images_dir
    return images_dir


@pytest.fixture
def other_users_project() -> str:
    """Create a second user plus a project they own; return the project id."""
    from db.models import ProjectRow, User
    from db.session import session_scope

    project_id = "proj-not-yours"
    with session_scope() as db:
        db.add(User(id=_OTHER_USER_ID, email="other-projects@example.com", is_active=True))
        db.add(ProjectRow(id=project_id, user_id=_OTHER_USER_ID, name="Their project"))
    return project_id


def _client() -> Any:
    from fastapi.testclient import TestClient
    from main import app

    return TestClient(app)


def test_create_list_rename_delete_round_trip(storage_sandbox: Path) -> None:
    client = _client()

    created = client.post("/projects", json={"name": "Apartment"})
    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Apartment"
    assert body["room_count"] == 0
    project_id = body["id"]

    listed = client.get("/projects")
    assert listed.status_code == 200
    assert any(p["id"] == project_id for p in listed.json())

    renamed = client.post(f"/projects/{project_id}/name", json={"name": "Loft"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Loft"

    deleted = client.delete(f"/projects/{project_id}")
    assert deleted.status_code == 204

    listed_after = client.get("/projects")
    assert all(p["id"] != project_id for p in listed_after.json())


def test_duplicate_project_name_conflicts(storage_sandbox: Path) -> None:
    client = _client()
    first = client.post("/projects", json={"name": "Apartment"})
    assert first.status_code == 201

    dup = client.post("/projects", json={"name": "Apartment"})
    assert dup.status_code == 409


def test_duplicate_rename_conflicts(storage_sandbox: Path) -> None:
    client = _client()
    client.post("/projects", json={"name": "Apartment"})
    second = client.post("/projects", json={"name": "Cabin"}).json()

    conflict = client.post(f"/projects/{second['id']}/name", json={"name": "Apartment"})
    assert conflict.status_code == 409


def test_other_users_project_404s_on_every_route(
    storage_sandbox: Path, other_users_project: str
) -> None:
    client = _client()
    cases: list[tuple[str, str, dict[str, Any]]] = [
        ("POST", f"/projects/{other_users_project}/name", {"json": {"name": "Mine now"}}),
        ("DELETE", f"/projects/{other_users_project}", {}),
    ]
    for method, path, kwargs in cases:
        response = client.request(method, path, **kwargs)
        assert response.status_code == 404, f"{method} {path} -> {response.status_code} {response.text}"
        assert response.json()["detail"] == _NOT_FOUND_DETAIL.format(project_id=other_users_project)


def test_unknown_project_404s_identically(storage_sandbox: Path) -> None:
    client = _client()
    unknown = "totally-unknown-project"
    response = client.post(f"/projects/{unknown}/name", json={"name": "x"})
    assert response.status_code == 404
    assert response.json()["detail"] == _NOT_FOUND_DETAIL.format(project_id=unknown)


def test_projects_list_excludes_other_users_projects(
    storage_sandbox: Path, other_users_project: str
) -> None:
    client = _client()
    client.post("/projects", json={"name": "Mine"})
    ids = {p["id"] for p in client.get("/projects").json()}
    assert other_users_project not in ids


def test_upload_into_project_and_room_count(storage_sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("api.routes.get_upload_validation_enabled", lambda: False)
    monkeypatch.setattr("api.routes.get_camera_calibration_enabled", lambda: False)
    monkeypatch.setattr("api.routes.get_normal_map_enabled", lambda: False)
    client = _client()

    project = client.post("/projects", json={"name": "Apartment"}).json()
    uploaded = client.post(
        "/images/upload",
        data={"project_id": project["id"]},
        files={"file": ("room.png", b"fake-png-bytes", "image/png")},
    )
    assert uploaded.status_code == 200
    uid = uploaded.json()["image_id"]

    rooms = client.get("/images/sessions", params={"project_id": project["id"]})
    assert rooms.status_code == 200
    assert [r["uid"] for r in rooms.json()] == [uid]

    summary = next(p for p in client.get("/projects").json() if p["id"] == project["id"])
    assert summary["room_count"] == 1
    assert summary["preview_uid"] == uid


def test_upload_into_other_users_project_404s(storage_sandbox: Path, other_users_project: str) -> None:
    client = _client()
    response = client.post(
        "/images/upload",
        data={"project_id": other_users_project},
        files={"file": ("room.png", b"fake-png-bytes", "image/png")},
    )
    assert response.status_code == 404


def test_delete_project_cascades_rooms_and_files(storage_sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("api.routes.get_upload_validation_enabled", lambda: False)
    monkeypatch.setattr("api.routes.get_camera_calibration_enabled", lambda: False)
    monkeypatch.setattr("api.routes.get_normal_map_enabled", lambda: False)
    client = _client()

    project = client.post("/projects", json={"name": "Apartment"}).json()
    uploaded = client.post(
        "/images/upload",
        data={"project_id": project["id"]},
        files={"file": ("room.png", b"fake-png-bytes", "image/png")},
    )
    uid = uploaded.json()["image_id"]
    assert list(storage_sandbox.glob(f"{uid}.*"))

    deleted = client.delete(f"/projects/{project['id']}")
    assert deleted.status_code == 204

    assert not list(storage_sandbox.glob(f"{uid}.*"))
    assert session_repo.get_session_owner(uid) is None
    assert project_repo.get_project_owner(project["id"]) is None


def test_default_project_created_on_bare_register_uid(storage_sandbox: Path) -> None:
    """`register_uid` with no project_id (every off-request caller) still
    resolves to a real project, "My Rooms", instead of failing the NOT NULL
    FK -- the whole point of `get_or_create_default_project`."""
    session_repo.register_uid("sess-bare")
    owner = session_repo.get_session_owner("sess-bare")
    assert owner is not None
    projects = project_repo.list_projects(owner)
    assert any(p.name == project_repo.DEFAULT_PROJECT_NAME for p in projects)
