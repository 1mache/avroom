from __future__ import annotations

"""Session-ownership guard.

Every route that resolves a session purely from the `uid` in its URL or JSON
body (or, indirectly, from `object_uuid` -> `metadata.session_id`) used to
trust that uid unconditionally -- no comparison against the caller ever
happened. Invisible under `AUTH_MODE=single_user` (one fixed user owns
everything); a real IDOR the moment `AUTH_MODE=jwt` ships real accounts.

`require_session_owner` closes that gap as one router-level dependency
(`dependencies=[Depends(require_session_owner)]` on the `APIRouter(...)`
constructor, not `main.py::include_router` -- several tests build a bare
`FastAPI(); include_router(router)` and bypass `main.py` entirely, and a
dependency declared there would silently vanish for exactly those tests).
"""

import json
import logging

from fastapi import Depends, HTTPException, Request

from core.auth.identity import current_user_id
from core.object_metadata import get_object_by_uuid
from core.repositories.session_repo import get_session_owner

logger = logging.getLogger(__name__)

_BODY_UID_FIELDS = ("uid", "image_id", "session_id")


async def _resolve_session_uid(request: Request) -> tuple[str, str] | None:
    """Find the session uid a request targets, in priority order.

    Returns `(session_uid, not_found_detail)`, where `not_found_detail` is
    what to raise on any mismatch -- worded from whichever identifier the
    client actually supplied, so a foreign `object_uuid` never leaks the
    session uid behind it (or vice versa): "doesn't exist" and "exists but
    isn't yours" always produce the identical message for that identifier.

    1. Path `uid` -- returned immediately, without ever touching the body.
       This is what keeps multipart routes (`/images/upload`,
       `/images/{uid}/objects/import`) safe: reading `request.body()` on a
       multipart request raises `RuntimeError: Stream consumed`, since
       `UploadFile` parsing drains the stream without caching it.
    2. Path `object_uuid` -- resolved to its owning session via
       `get_object_by_uuid`. A missing object 404s here with the same
       message the route itself would use, so no route-level check changes.
    3. A JSON body's `uid` / `image_id` / `session_id` field -- only
       attempted for a JSON content-type, so a malformed or multipart body
       never reaches `json.loads`.

    Returns `None` when nothing matches (upload, the sessions list, `/jobs`,
    `/debug`), which `require_session_owner` treats as "not session-scoped,
    no check".
    """
    uid = request.path_params.get("uid")
    if uid is not None:
        return uid, f"Session not found for uid='{uid}'"

    object_uuid = request.path_params.get("object_uuid")
    if object_uuid is not None:
        detail = f"Object not found for uuid='{object_uuid}'"
        metadata = get_object_by_uuid(object_uuid)
        if metadata is None:
            raise HTTPException(status_code=404, detail=detail)
        return metadata.session_id, detail

    if request.method in ("POST", "PUT", "PATCH") and request.headers.get(
        "content-type", ""
    ).startswith("application/json"):
        try:
            body = json.loads(await request.body())
        except (ValueError, TypeError):
            return None
        if isinstance(body, dict):
            for field in _BODY_UID_FIELDS:
                value = body.get(field)
                if isinstance(value, str):
                    return value, f"Session not found for uid='{value}'"

    return None


async def require_session_owner(request: Request, user_id: str = Depends(current_user_id)) -> None:
    """404 (never 403) when the resolved session isn't owned by the caller.

    One comparison covers both "no such session" and "someone else's
    session" -- identical 404, identical detail string per identifier, no
    existence oracle. Mirrors the ownership check
    `core/repositories/job_repo.py::get_job` already does for jobs.
    """
    resolved = await _resolve_session_uid(request)
    if resolved is None:
        return
    uid, not_found_detail = resolved
    owner = get_session_owner(uid)
    if owner != user_id:
        logger.warning(
            "Session ownership check failed: uid=%s caller=%s owner=%s", uid, user_id, owner
        )
        raise HTTPException(status_code=404, detail=not_found_detail)
