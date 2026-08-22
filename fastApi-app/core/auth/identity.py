from __future__ import annotations

"""Resolves "who is asking" for one HTTP request.

This is the single seam `AUTH_MODE=jwt` will change: swap the body of
`current_user_id` for one that reads/validates an `Authorization: Bearer`
token instead of always returning the fixed local user. Every route that
needs a caller identity (all `/jobs` routes, plus the three job-submit
routes) depends on this function rather than resolving identity itself, so
that swap touches one place, not every route.
"""

from core.auth.single_user import get_default_user_id
from db.session import session_scope


def current_user_id() -> str:
    """Return the id of the user making the current request.

    `AUTH_MODE=single_user` (the only mode implemented today) always returns
    the fixed local dev user, auto-provisioning its row if needed.
    """
    with session_scope() as db:
        return get_default_user_id(db)
