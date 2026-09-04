from __future__ import annotations

"""The `AUTH_MODE=single_user` local dev user.

Every session/object still carries a real `user_id` foreign key so the same
schema works unchanged once `AUTH_MODE=jwt` (Phase 5: login, ownership checks
on every route) replaces this fixed lookup with one derived from a bearer
token — no migration needed then, only the resolution of "who is asking".
"""

import logging

from sqlalchemy.orm import Session

from core.auth.jwt_backend import hash_password
from db.models import User

logger = logging.getLogger(__name__)

# Fixed so the same local user is reused across restarts instead of a fresh
# row (and a fresh set of "your" sessions) appearing every boot.
LOCAL_USER_ID = "00000000-0000-0000-0000-000000000001"
LOCAL_USER_EMAIL = "avroom-team@proton.me"

# Intentionally weak -- this row only exists on local dev / single_user
# machines, never on a real deploy, and only matters so `AUTH_MODE=jwt` can
# still log in as it (`POST /auth/login`) instead of the fixed identity being
# unreachable under `jwt` mode.
LOCAL_USER_PASSWORD = "admin"


def get_or_create_default_user(db: Session) -> User:
    """Return the fixed local dev user, creating it (or backfilling its password) on first call."""
    user = db.get(User, LOCAL_USER_ID)
    if user is not None:
        if user.password_hash is None:
            user.password_hash = hash_password(LOCAL_USER_PASSWORD)
            db.flush()
            logger.info("Backfilled local dev user password: id=%s", user.id)
        return user

    user = User(
        id=LOCAL_USER_ID,
        email=LOCAL_USER_EMAIL,
        password_hash=hash_password(LOCAL_USER_PASSWORD),
        is_active=True,
        is_admin=True,
    )
    db.add(user)
    db.flush()
    logger.info("Provisioned local dev user: id=%s email=%s", user.id, user.email)
    return user


def get_default_user_id(db: Session) -> str:
    """Return the fixed local dev user's id, provisioning the row if needed."""
    return get_or_create_default_user(db).id
