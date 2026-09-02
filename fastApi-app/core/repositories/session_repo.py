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


def _get_session_row_or_raise(db: Session, uid: str) -> SessionRow:
    """Return the session row for *uid*.

    Raises:
        SessionNotFoundError: When no session row exists for *uid*.
    """
    row = db.get(SessionRow, uid)
    if row is None:
        raise SessionNotFoundError(uid)
    return row


def register_uid(uid: str, user_id: str | None = None) -> None:
    """Register a session uid, creating its row (owned by *user_id*) if absent.

    The only creation path left in this module -- `touch_session` and
    `set_session_name` used to also create on a miss (via the old
    `_get_or_create_session_row`, which resolved the owner by calling
    `core.auth.identity.current_user_id()` directly, off any request). That
    call became impossible once `current_user_id` gained a mandatory
    `request: Request` parameter for `AUTH_MODE=jwt` -- and it was already
    the wrong behavior: touching a deleted session mid-job used to silently
    resurrect a ghost row owned by whichever fixed identity the bare call
    resolved to, regardless of who actually owned it. Now a touch/rename
    against a since-deleted uid raises `SessionNotFoundError` instead, which
    every real caller already reaches through `core.auth.ownership`'s guard
    (or, for the handful of off-request callers, is a legitimate job
    failure).

    `user_id` defaults to the fixed local dev user (auto-provisioning that
    row too, exactly like the old `current_user_id()` path did) so the ~15
    call sites that only ever ran under `AUTH_MODE=single_user` (tests, the
    sidecar migration script, `object_metadata`'s defensive re-registration)
    need no change -- this deliberately does *not* consult `AUTH_MODE`
    itself, since an off-request caller always means "the local dev user",
    regardless of what a `jwt`-mode env happens to be set to.
    `api/routes.py`'s upload handler -- the one place a uid is actually born
    under a real caller -- passes its own resolved `user_id` explicitly.
    """
    with session_scope() as db:
        row = db.get(SessionRow, uid)
        if row is not None:
            return
        resolved_user_id = user_id if user_id is not None else get_default_user_id(db)
        db.add(SessionRow(id=uid, user_id=resolved_user_id, name=None, last_changed=None))


def is_session_registered(uid: str) -> bool:
    """Return whether a session row exists for *uid*."""
    with session_scope() as db:
        return db.get(SessionRow, uid) is not None


def get_session_owner(uid: str) -> str | None:
    """Return the `user_id` owning *uid*, or `None` if unregistered.

    The whole ownership primitive: `core.auth.ownership.require_session_owner`
    compares this against the caller's id, and a mismatch (including `None`)
    produces the same 404 as an unknown uid -- no existence oracle.
    """
    with session_scope() as db:
        row = db.get(SessionRow, uid)
        return row.user_id if row is not None else None


def load_session_uids() -> list[str]:
    """Return every registered session uid, oldest first."""
    with session_scope() as db:
        rows = db.execute(select(SessionRow.id).order_by(SessionRow.created_at)).scalars().all()
        return list(rows)


def get_session_name(uid: str) -> str | None:
    """Return the human-readable name for *uid*, or `None` if unset/unknown."""
    with session_scope() as db:
        row = db.get(SessionRow, uid)
        return row.name if row is not None else None


def set_session_name(uid: str, name: str) -> None:
    """Persist a human-readable name for a session uid.

    Names are unique per user. Raises ValueError if `name` is already
    assigned to a *different* session so the caller can surface a 409.

    Raises:
        SessionNotFoundError: When no session row exists for *uid*.
    """
    with session_scope() as db:
        row = _get_session_row_or_raise(db, uid)

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

    Raises:
        SessionNotFoundError: When no session row exists for *uid* -- e.g.
            the session was deleted while a queued job targeting it was
            still in flight (see `register_uid`'s docstring).
    """
    with session_scope() as db:
        row = _get_session_row_or_raise(db, uid)
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
    when unnamed (the normal case). Returns None when the uid isn't registered,
    so callers can no-op a
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


def list_sessions_with_names(user_id: str) -> list[tuple[str, str | None, str | None]]:
    """Return `(uid, name, last_changed_iso)` for *user_id*'s sessions, oldest first.

    Single round trip for `GET /images/sessions`, avoiding the old
    load_session_uids + load_names + per-uid get_session_last_changed
    N+1 pattern. Scoped to `user_id` so one caller never sees another's
    sessions in the list.
    """
    with session_scope() as db:
        rows = db.execute(
            select(SessionRow)
            .where(SessionRow.user_id == user_id)
            .order_by(SessionRow.created_at)
        ).scalars().all()
        return [
            (row.id, row.name, row.last_changed.isoformat() if row.last_changed else None)
            for row in rows
        ]
