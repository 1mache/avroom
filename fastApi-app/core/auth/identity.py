from __future__ import annotations

"""Resolves "who is asking" for one HTTP request.

The single seam `AUTH_MODE` branches on: `single_user` (the local-dev
default) always returns the fixed local user, auto-provisioning its row if
needed; `jwt` reads and validates an `Authorization: Bearer` token instead.
Every route that needs a caller identity depends on this function via
`Depends(current_user_id)` rather than resolving identity itself, so the
branch lives in one place, not every route.
"""

import logging

from fastapi import HTTPException, Request

from core.auth.jwt_backend import AuthError, decode_token
from core.auth.single_user import get_default_user_id
from db.session import session_scope
from settings import get_auth_mode

logger = logging.getLogger(__name__)

_WWW_AUTHENTICATE = {"WWW-Authenticate": "Bearer"}


def current_user_id(request: Request) -> str:
    """Return the id of the user making the current request.

    `request` is unused in `single_user` mode but required in `jwt` mode (to
    read the `Authorization` header) -- FastAPI injects it automatically for
    every `Depends(current_user_id)` call site, so this signature change
    touches no caller.
    """
    if get_auth_mode() != "jwt":
        with session_scope() as db:
            return get_default_user_id(db)

    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        # <img src> can't set an Authorization header, so the three routes
        # rendered that way (background/original/preview) fall back to a
        # query param. Every other route still only ever sees the header.
        token = request.query_params.get("token", "")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated", headers=_WWW_AUTHENTICATE)
    try:
        return decode_token(token)
    except AuthError as exc:
        logger.warning("Token rejected: %s", exc)
        raise HTTPException(
            status_code=401, detail="Invalid or expired token", headers=_WWW_AUTHENTICATE
        ) from None
