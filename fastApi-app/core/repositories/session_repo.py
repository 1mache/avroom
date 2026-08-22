from __future__ import annotations

"""Postgres-backed session registry and metadata.

Replaces the four JSON sidecars (`sessions.json`, `names.json`,
`session_timestamps.json`) that used to live one directory above the image
storage dir. Function names/shapes match those sidecar helpers so call sites
only had to drop the module they import from.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.auth.single_user import get_default_user_id
from db.models import SessionRow, User
from db.session import session_scope

logger = logging.getLogger(__name__)


class SessionNotFoundError(LookupError):
    """Raised when a sync-check (or other lookup) targets an unknown uid."""


def _get_or_create_session_row(db: Session, uid: str) -> SessionRow:
    """Return the session row for *uid*, creating it (owned by the local dev
    user) if absent.

    `AUTH_MODE=jwt` (Phase 5) will thread a real caller-derived user id
    through here instead of always resolving the fixed local user.
    """
    row = db.get(SessionRow, uid)
    if row is not None:
        return row
    row = SessionRow(id=uid, user_id=get_default_user_id(db), name=None, last_changed=None)
    db.add(row)
    db.flush()
    return row


def register_uid(uid: str) -> None:
    """Register a session uid, creating its row if it doesn't already exist."""
    with session_scope() as db:
        _get_or_create_session_row(db, uid)


def is_session_registered(uid: str) -> bool:
    """Return whether a session row exists for *uid*."""
    with session_scope() as db:
        return db.get(SessionRow, uid) is not None


def load_session_uids() -> list[str]:
    """Return every registered session uid, oldest first."""
    with session_scope() as db:
        rows = db.execute(select(SessionRow.id).order_by(SessionRow.created_at)).scalars().all()
        return list(rows)


def load_names() -> dict[str, str]:
    """Return the uid -> name mapping for every named session."""
    with session_scope() as db:
        rows = db.execute(
            select(SessionRow.id, SessionRow.name).where(SessionRow.name.is_not(None))
        ).all()
        return {uid: name for uid, name in rows if name is not None}


def set_session_name(uid: str, name: str) -> None:
    """Persist a human-readable name for a session uid.

    Names are unique per user. Raises ValueError if `name` is already
    assigned to a *different* session so the caller can surface a 409.
    """
    with session_scope() as db:
        row = _get_or_create_session_row(db, uid)

        existing = db.execute(
            select(SessionRow.id).where(
                SessionRow.user_id == row.user_id,
                SessionRow.name == name,
                SessionRow.id != uid,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ValueError(f"Name '{name}' is already used by another session.")

        row.name = name
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise ValueError(f"Name '{name}' is already used by another session.") from exc


def touch_session(uid: str) -> str:
    """Record a fresh last-changed timestamp for one session and return it.

    Creates the session row if it doesn't exist yet, matching the old
    sidecars' decoupled behavior (a timestamp could be written for a uid
    never explicitly registered).
    """
    with session_scope() as db:
        row = _get_or_create_session_row(db, uid)
        row.last_changed = datetime.now(UTC)
        db.flush()
        return row.last_changed.isoformat()


def get_session_last_changed(uid: str) -> str | None:
    """Return the persisted last-changed timestamp for a session, if any."""
    with session_scope() as db:
        row = db.get(SessionRow, uid)
        if row is None or row.last_changed is None:
            return None
        return row.last_changed.isoformat()


def evaluate_session_sync(uid: str, client_last_changed: str | None) -> tuple[str, bool]:
    """Compare client and server session timestamps.

    Returns:
        Tuple of ``(server_last_changed, needs_refresh)``. ``server_last_changed``
        is an empty string when the session exists but has no recorded timestamp.

    Raises:
        SessionNotFoundError: When no session row exists for *uid*.
    """
    with session_scope() as db:
        row = db.get(SessionRow, uid)
        if row is None:
            raise SessionNotFoundError(uid)
        server_last_changed = row.last_changed.isoformat() if row.last_changed else ""
        needs_refresh = client_last_changed != server_last_changed
        return server_last_changed, needs_refresh


def clear_session_last_changed(uid: str) -> None:
    """Clear one session's last-changed timestamp. No-op when the row is absent."""
    with session_scope() as db:
        row = db.get(SessionRow, uid)
        if row is None:
            return
        row.last_changed = None


def delete_session(uid: str) -> None:
    """Delete a session row and cascade-delete every object row under it.

    No-op if the uid is not registered. Does not touch any files on disk —
    callers are responsible for deleting the associated blobs first (they
    need the object ids from :func:`core.object_metadata.list_object_ids`,
    which this call would otherwise wipe out).
    """
    with session_scope() as db:
        row = db.get(SessionRow, uid)
        if row is None:
            return
        db.delete(row)


def get_session_notify_target(uid: str) -> tuple[str, str] | None:
    """Return ``(display_name, recipient_email)`` for a session's owner.

    `display_name` is the session's name, falling back to the uid itself
    when unnamed (the normal case — see `_get_or_create_session_row`).
    Returns None when the uid isn't registered, so callers can no-op a
    notification for an unknown session instead of raising.
    """
    with session_scope() as db:
        row = db.execute(
            select(SessionRow.name, User.email)
            .join(User, User.id == SessionRow.user_id)
            .where(SessionRow.id == uid)
        ).one_or_none()
        if row is None:
            return None
        name, email = row
        return (name or uid, email)


def list_sessions_with_names() -> list[tuple[str, str | None, str | None]]:
    """Return `(uid, name, last_changed_iso)` for every session, oldest first.

    Single round trip for `GET /images/sessions`, avoiding the old
    load_session_uids + load_names + per-uid get_session_last_changed
    N+1 pattern.
    """
    with session_scope() as db:
        rows = db.execute(select(SessionRow).order_by(SessionRow.created_at)).scalars().all()
        return [
            (row.id, row.name, row.last_changed.isoformat() if row.last_changed else None)
            for row in rows
        ]
