from __future__ import annotations

"""Admin-only gate.

`is_admin` on `users` is a plain boolean with no grant API -- it is flipped
by hand in SQL (see the migration `0007_user_is_admin` docstring). Two
call sites use it: the `/debug` router (hard 403 via `require_admin`, a
router-level dependency mirroring `core/auth/ownership.py::require_session_owner`)
and the upload endpoint's `skip_validation` flag (a plain boolean check via
`is_admin`, since that route must still work for non-admins with the flag
left off).
"""

import logging

from fastapi import Depends, HTTPException

from core.auth.identity import current_user_id
from db.models import User
from db.session import session_scope

logger = logging.getLogger(__name__)


def is_admin(user_id: str) -> bool:
    """Return whether the given user's row has `is_admin` set.

    False for an unknown user id rather than raising -- callers already know
    the id is valid (it came from `current_user_id`), so this only matters
    for the theoretical case of a deleted-mid-request row.
    """
    with session_scope() as db:
        user = db.get(User, user_id)
        return bool(user and user.is_admin)


def require_admin(user_id: str = Depends(current_user_id)) -> str:
    """403 unless the caller's user row has `is_admin` set.

    Unlike `require_session_owner`, there is no existence to leak (every
    caller already resolved to a real user id via `current_user_id`), so a
    plain 403 is used instead of a 404.
    """
    if not is_admin(user_id):
        logger.warning("Admin check failed: user_id=%s", user_id)
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user_id
