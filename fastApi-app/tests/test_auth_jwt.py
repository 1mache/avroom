"""Tests for AUTH_MODE=jwt (core/auth/jwt_backend.py, core/auth/identity.py,
api/auth.py) and the corresponding single_user-mode-is-unchanged guarantee.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import jwt as pyjwt
import pytest

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))


def _client() -> Any:
    from fastapi.testclient import TestClient
    from main import app

    return TestClient(app)


def _signup(client: Any, email: str = "alice@example.com", password: str = "hunter2ok") -> str:
    response = client.post("/auth/signup", json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    token: str = response.json()["access_token"]
    return token


# ---------------------------------------------------------------------------
# AUTH_MODE=jwt
# ---------------------------------------------------------------------------


def test_signup_returns_usable_token(jwt_mode: None) -> None:
    client = _client()
    token = _signup(client, "alice@example.com")

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == "alice@example.com"


def test_signup_duplicate_email_409(jwt_mode: None) -> None:
    client = _client()
    _signup(client, "dupe@example.com")

    response = client.post(
        "/auth/signup", json={"email": "dupe@example.com", "password": "anotherok1"}
    )
    assert response.status_code == 409


def test_signup_rejects_short_password_422(jwt_mode: None) -> None:
    response = _client().post("/auth/signup", json={"email": "x@example.com", "password": "short"})
    assert response.status_code == 422


def test_signup_rejects_password_over_72_bytes_422(jwt_mode: None) -> None:
    """Pins core/auth/jwt_backend.py's bcrypt-limit note: this must be a
    clean 422 from schema validation, not a 500 from bcrypt itself."""
    response = _client().post(
        "/auth/signup", json={"email": "x@example.com", "password": "a" * 100}
    )
    assert response.status_code == 422


def test_login_wrong_password_401(jwt_mode: None) -> None:
    client = _client()
    _signup(client, "bob@example.com", "correct-pw1")

    response = client.post("/auth/login", json={"email": "bob@example.com", "password": "wrong-pw1"})
    assert response.status_code == 401
    wrong_password_detail = response.json()["detail"]

    unknown = client.post("/auth/login", json={"email": "nobody@example.com", "password": "wrong-pw1"})
    assert unknown.status_code == 401
    # Identical status and detail for "wrong password" vs "no such account" --
    # no user-enumeration oracle.
    assert unknown.json()["detail"] == wrong_password_detail


def test_login_inactive_user_401(jwt_mode: None) -> None:
    from db.models import User
    from db.session import session_scope

    client = _client()
    token = _signup(client, "carol@example.com", "correct-pw1")
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()

    with session_scope() as db:
        row = db.get(User, me["user_id"])
        assert row is not None
        row.is_active = False

    response = client.post(
        "/auth/login", json={"email": "carol@example.com", "password": "correct-pw1"}
    )
    assert response.status_code == 401


def test_me_without_token_401(jwt_mode: None) -> None:
    response = _client().get("/auth/me")
    assert response.status_code == 401


def test_me_with_garbage_token_401(jwt_mode: None) -> None:
    response = _client().get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_me_with_expired_token_401(jwt_mode: None) -> None:
    import time
    from datetime import UTC, datetime, timedelta

    expired = pyjwt.encode(
        {"sub": "whoever", "exp": datetime.now(UTC) - timedelta(minutes=1)},
        "test-secret-not-for-production",
        algorithm="HS256",
    )
    time.sleep(0)  # no-op; keeps the expiry construction adjacent to use
    response = _client().get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


def test_me_with_token_signed_by_wrong_secret_401(jwt_mode: None) -> None:
    forged = pyjwt.encode({"sub": "whoever"}, "not-the-real-secret", algorithm="HS256")
    response = _client().get("/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_jwt_mode_without_secret_fails_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient
    from main import app

    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.delenv("JWT_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        with TestClient(app):
            pass


def test_two_users_cannot_see_each_others_sessions(jwt_mode: None) -> None:
    """Phase 1 (ownership guard) and Phase 2 (real accounts) proving each
    other: two independently signed-up users, one session each, neither
    reachable by the other's token."""
    from core.repositories import session_repo

    client = _client()
    token_a = _signup(client, "session-a-owner@example.com")
    token_b = _signup(client, "session-b-owner@example.com")
    user_a_id = client.get("/auth/me", headers={"Authorization": f"Bearer {token_a}"}).json()[
        "user_id"
    ]

    uid = "sess-owned-by-a"
    session_repo.register_uid(uid, user_a_id)

    mine = client.get(f"/images/{uid}/cache", headers={"Authorization": f"Bearer {token_a}"})
    assert mine.status_code == 200

    theirs = client.get(f"/images/{uid}/cache", headers={"Authorization": f"Bearer {token_b}"})
    assert theirs.status_code == 404
    assert theirs.json()["detail"] == f"Session not found for uid='{uid}'"


# ---------------------------------------------------------------------------
# AUTH_MODE=single_user (default) stays unchanged
# ---------------------------------------------------------------------------


def test_single_user_mode_needs_no_token() -> None:
    response = _client().get("/images/sessions")
    assert response.status_code == 200


def test_single_user_mode_ignores_a_bogus_bearer_header() -> None:
    """The mode branch must run before any token decode -- a garbage header
    must never 401 in single_user mode."""
    response = _client().get(
        "/images/sessions", headers={"Authorization": "Bearer complete-garbage"}
    )
    assert response.status_code == 200


def test_single_user_mode_resolves_the_fixed_local_user() -> None:
    from core.auth.single_user import LOCAL_USER_ID

    from core.repositories import session_repo

    session_repo.register_uid("sess-1")
    assert session_repo.get_session_owner("sess-1") == LOCAL_USER_ID


def test_bad_auth_mode_value_degrades_to_single_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_MODE", "nonsense")
    response = _client().get("/images/sessions")
    assert response.status_code == 200
