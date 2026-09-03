from __future__ import annotations

"""Postgres-backed project registry.

Projects sit above sessions (rooms): `User -> Project -> Room`. Mirrors
`session_repo.py`'s convention -- every function opens its own
`session_scope()` -- with one exception (`get_or_create_default_project`,
see its docstring) that instead takes an existing `Session` so it can run
inside a caller's transaction.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models import ProjectRow, SessionRow
from db.session import session_scope

logger = logging.getLogger(__name__)

DEFAULT_PROJECT_NAME = "My Rooms"


class ProjectNotFoundError(LookupError):
    """Raised when a lookup targets an unknown project id."""


@dataclass
class ProjectSummary:
    """One project plus the room-derived fields the dashboard needs.

    `last_changed`/`preview_uid` are computed over the project's rooms (most
    recently edited room wins) rather than stored -- a project has no preview
    blob of its own, it borrows its most-recent room's.
    """

    id: str
    name: str
    room_count: int
    last_changed: str | None
    preview_uid: str | None


def _get_project_row_or_raise(db: Session, project_id: str) -> ProjectRow:
    row = db.get(ProjectRow, project_id)
    if row is None:
        raise ProjectNotFoundError(project_id)
    return row


def create_project(user_id: str, name: str) -> str:
    """Create a new project for *user_id* and return its id.

    Raises:
        ValueError: When *name* is already used by another of this user's projects.
    """
    with session_scope() as db:
        existing = db.execute(
            select(ProjectRow.id).where(ProjectRow.user_id == user_id, ProjectRow.name == name)
        ).scalar_one_or_none()
        if existing is not None:
            raise ValueError(f"Name '{name}' is already used by another project.")

        row = ProjectRow(user_id=user_id, name=name)
        db.add(row)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise ValueError(f"Name '{name}' is already used by another project.") from exc
        return row.id


def get_project_owner(project_id: str) -> str | None:
    """Return the `user_id` owning *project_id*, or `None` if unregistered.

    The ownership primitive for `core.auth.ownership.require_project_owner`,
    mirroring `session_repo.get_session_owner`.
    """
    with session_scope() as db:
        row = db.get(ProjectRow, project_id)
        return row.user_id if row is not None else None


def get_or_create_default_project(db: Session, user_id: str) -> str:
    """Return *user_id*'s "My Rooms" project id, creating it if absent.

    Takes an existing `Session` (unlike every other function in this module)
    so `session_repo.register_uid` can resolve it inside the same transaction
    that creates the session row -- mirroring how
    `core.auth.single_user.get_default_user_id(db)` already resolves the
    fixed local user inside that same call. This keeps "first upload for a
    brand-new user" atomic: either both the default project and the session
    exist afterward, or neither does.
    """
    row = db.execute(
        select(ProjectRow).where(ProjectRow.user_id == user_id, ProjectRow.name == DEFAULT_PROJECT_NAME)
    ).scalar_one_or_none()
    if row is not None:
        return row.id

    row = ProjectRow(user_id=user_id, name=DEFAULT_PROJECT_NAME)
    db.add(row)
    db.flush()
    logger.info("Provisioned default project: id=%s user_id=%s", row.id, user_id)
    return row.id


def set_project_name(project_id: str, name: str) -> None:
    """Persist a human-readable name for a project.

    Raises:
        ProjectNotFoundError: When no project row exists for *project_id*.
        ValueError: When *name* is already used by another of this user's projects.
    """
    with session_scope() as db:
        row = _get_project_row_or_raise(db, project_id)

        existing = db.execute(
            select(ProjectRow.id).where(
                ProjectRow.user_id == row.user_id,
                ProjectRow.name == name,
                ProjectRow.id != project_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ValueError(f"Name '{name}' is already used by another project.")

        row.name = name
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise ValueError(f"Name '{name}' is already used by another project.") from exc


def list_projects(user_id: str) -> list[ProjectSummary]:
    """Return *user_id*'s projects, newest first, each with its room-derived fields.

    Two queries total (projects, then their sessions) folded in Python --
    projects per user are a handful, so this beats a correlated subquery for
    no real cost.
    """
    with session_scope() as db:
        projects = db.execute(
            select(ProjectRow).where(ProjectRow.user_id == user_id).order_by(ProjectRow.created_at.desc())
        ).scalars().all()
        if not projects:
            return []

        project_ids = [p.id for p in projects]
        sessions = db.execute(
            select(SessionRow.project_id, SessionRow.id, SessionRow.last_changed).where(
                SessionRow.project_id.in_(project_ids)
            )
        ).all()

        rooms_by_project: dict[str, list[tuple[str, datetime | None]]] = {}
        for project_id, session_id, last_changed in sessions:
            rooms_by_project.setdefault(project_id, []).append((session_id, last_changed))

        summaries: list[ProjectSummary] = []
        for project in projects:
            rooms = rooms_by_project.get(project.id, [])
            last_changed_iso: str | None = None
            preview_uid: str | None = None
            timed_rooms = [(sid, lc) for sid, lc in rooms if lc is not None]
            if timed_rooms:
                preview_uid, latest = max(timed_rooms, key=lambda pair: pair[1])
                last_changed_iso = latest.isoformat()
            summaries.append(
                ProjectSummary(
                    id=project.id,
                    name=project.name,
                    room_count=len(rooms),
                    last_changed=last_changed_iso,
                    preview_uid=preview_uid,
                )
            )
        return summaries


def get_project(project_id: str) -> ProjectSummary | None:
    """Return one project's summary (room-derived fields included), or None if unknown.

    Used by `POST /projects/{id}/name` to hand back the same shape
    `list_projects` produces without duplicating its aggregation for a
    single-project response.
    """
    with session_scope() as db:
        project = db.get(ProjectRow, project_id)
        if project is None:
            return None
        rooms = db.execute(
            select(SessionRow.id, SessionRow.last_changed).where(SessionRow.project_id == project_id)
        ).all()
        timed_rooms = [(sid, lc) for sid, lc in rooms if lc is not None]
        last_changed_iso: str | None = None
        preview_uid: str | None = None
        if timed_rooms:
            preview_uid, latest = max(timed_rooms, key=lambda pair: pair[1])
            last_changed_iso = latest.isoformat()
        return ProjectSummary(
            id=project.id,
            name=project.name,
            room_count=len(rooms),
            last_changed=last_changed_iso,
            preview_uid=preview_uid,
        )


def list_project_session_ids(project_id: str) -> list[str]:
    """Return every session id under *project_id*."""
    with session_scope() as db:
        rows = db.execute(select(SessionRow.id).where(SessionRow.project_id == project_id)).scalars().all()
        return list(rows)


def delete_project_row(project_id: str) -> None:
    """Delete a project row. No-op if the id is not registered.

    Callers must delete every room under it (and its files) first via
    `core.session_teardown.delete_session_and_files` -- the FK cascade would
    otherwise delete the `SessionRow`s here without cleaning up their blobs,
    exactly like `session_repo.delete_session` for objects.
    """
    with session_scope() as db:
        row = db.get(ProjectRow, project_id)
        if row is None:
            return
        db.delete(row)
