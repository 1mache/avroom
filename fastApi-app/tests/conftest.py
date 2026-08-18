from __future__ import annotations

"""Shared pytest configuration for `fastApi-app/tests`.

Puts `fastApi-app/` on `sys.path` once, at collection time, so test modules
can `import core...` / `import api...` without each repeating its own
`sys.path` hack (several still do, harmlessly — this makes that redundant
rather than replacing them outright).

Also owns the Postgres fixture: session/object metadata now lives in
Postgres (see docs/deployment/aws-runbook.md), one dialect only per the AWS
deployment plan — no SQLite hedging for tests. Requires `docker compose up
db` running locally (`DATABASE_URL` defaults to that instance).
"""

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import text

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))


@pytest.fixture(autouse=True)
def _clean_database() -> Iterator[None]:
    """Ensure the schema exists and every table is empty before each test."""
    from db import models  # noqa: F401 — registers tables on Base.metadata
    from db.base import Base
    from db.session import get_engine

    engine = get_engine()
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE objects, sessions, users RESTART IDENTITY CASCADE"))
    yield
