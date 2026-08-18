from __future__ import annotations

"""Engine + session plumbing.

`get_engine()` is a per-process lazy singleton, the same pattern used by
`SamFacadeSingleton` and the depth-map `lru_cache`d loaders: each process
(the API process, or a spawned `INFERENCE_WORKERS>0` subprocess) builds its
own engine and connection pool on first use rather than inheriting one across
a `spawn` boundary.
"""

import functools
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from settings import get_database_url


@functools.lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return this process's singleton SQLAlchemy engine."""
    return create_engine(get_database_url(), pool_pre_ping=True, future=True)


@functools.lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Open a short-lived session, commit on success, roll back on error.

    Every repository function in `core/object_metadata.py` and
    `core/repositories/session_repo.py` opens its own session via this
    context manager rather than taking one as a parameter — mirroring how the
    JSON sidecars they replace were self-contained read/write calls, so call
    sites elsewhere needed no signature changes beyond dropping the old
    `base_dir` argument.
    """
    session = _session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session.

    Not required by the self-contained repository functions above; reserved
    for future auth routes (Phase 5) that need explicit transactional control.
    """
    with session_scope() as session:
        yield session
