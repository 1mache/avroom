from __future__ import annotations

"""Shared pytest configuration for `fastApi-app/tests`.

Puts `fastApi-app/` on `sys.path` once, at collection time, so test modules
can `import core...` / `import api...` without each repeating its own
`sys.path` hack (several still do, harmlessly — this makes that redundant
rather than replacing them outright).

Also owns the Postgres fixture: session/object metadata now lives in
Postgres (see docs/deployment/aws-runbook.md), one dialect only per the AWS
deployment plan — no SQLite hedging for tests. Requires `docker compose up
db` running locally.

Tests run against a dedicated `<dbname>_test` database, never the dev
database the app itself uses — `_use_test_database()` below repoints
`DATABASE_URL` (creating the database on first run if needed) before
anything in the test process can cache an engine against the real one.
Without this, the autouse `TRUNCATE` below would wipe live dev/session data
on every `pytest` run.
"""

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))


def _use_test_database() -> None:
    """Point `DATABASE_URL` at a dedicated `<dbname>_test` database, creating
    it if absent, before `db.session.get_engine()` (process-wide cached) is
    ever called.
    """
    from settings import get_database_url

    base_url = make_url(get_database_url())
    test_url = base_url.set(database=f"{base_url.database}_test")
    # str(url) masks the password as "***" — must render it explicitly or
    # DATABASE_URL ends up with a literal "***" password.
    os.environ["DATABASE_URL"] = test_url.render_as_string(hide_password=False)

    maintenance_engine = create_engine(base_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with maintenance_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": test_url.database},
        ).scalar_one_or_none()
        if exists is None:
            conn.execute(text(f'CREATE DATABASE "{test_url.database}"'))
    maintenance_engine.dispose()


_use_test_database()


@pytest.fixture(scope="session", autouse=True)
def _ensure_test_schema() -> None:
    """Recreate tables once per pytest process so columns match current models.

    ``create_all`` alone does not add columns to an existing table; a stale
    ``avroom_test`` schema from before a migration would then fail every test
    that touches the new columns.
    """
    from db import models  # noqa: F401 — registers tables on Base.metadata
    from db.base import Base
    from db.session import get_engine

    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


@pytest.fixture(autouse=True)
def _clean_database() -> Iterator[None]:
    """Ensure every table is empty before each test."""
    from db.session import get_engine

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE objects, sessions, projects, users RESTART IDENTITY CASCADE"))
    yield


OTHER_USER_ID = "00000000-0000-0000-0000-000000000099"


@pytest.fixture
def other_users_session() -> str:
    """Create a second user plus a session they own; return the session's uid.

    The shared fixture for every "not my session" ownership test: a request
    authenticated as the default local user must 404 against this uid exactly
    like an unknown one.
    """
    from db.models import ProjectRow, SessionRow, User
    from db.session import session_scope

    uid = "sess-not-yours"
    project_id = "proj-not-yours"
    with session_scope() as db:
        db.add(User(id=OTHER_USER_ID, email="other@example.com", is_active=True))
        db.add(ProjectRow(id=project_id, user_id=OTHER_USER_ID, name="My Rooms"))
        db.add(
            SessionRow(id=uid, user_id=OTHER_USER_ID, project_id=project_id, name=None, last_changed=None)
        )
    return uid


@pytest.fixture
def jwt_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Switch AUTH_MODE to jwt for one test, with a throwaway signing secret.

    Safe because `settings.get_auth_mode()`/`get_jwt_secret()` read
    `os.environ` fresh on every call -- nothing to un-cache on teardown.
    """
    monkeypatch.setenv("AUTH_MODE", "jwt")
    monkeypatch.setenv("JWT_SECRET", "test-secret-not-for-production")
