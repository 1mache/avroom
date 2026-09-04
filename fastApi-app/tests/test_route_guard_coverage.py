"""Anti-fail-open guard: every session-scoped route must carry the ownership
dependency (core/auth/ownership.py::require_session_owner).

A router-level `dependencies=[Depends(require_session_owner)]` is fail-closed
for new routes added to an *existing* router, but two holes remain: a brand
new router nobody adds the dependency to, or a new uid-carrying param/field
name the resolver doesn't know about. This file is the standing guard against
both -- it walks the real, fully-assembled `main.app` route table and fails
loudly if a route that looks session-scoped doesn't carry the guard.
"""

from __future__ import annotations

import sys
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parents[1]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from fastapi.routing import APIRoute  # noqa: E402

from core.auth.ownership import require_project_owner, require_session_owner  # noqa: E402
from main import app  # noqa: E402

_UID_PATH_PARAMS = {"uid", "object_uuid"}
_UID_BODY_FIELDS = {"uid", "image_id", "session_id"}
_PROJECT_PATH_PARAMS = {"project_id"}

# Routes deliberately exempt from the guard, reviewed and justified below.
# Keep this present-but-empty: any addition must be a visible diff.
_EXEMPT: set[tuple[str, str]] = set()


def _is_session_scoped(route: APIRoute) -> bool:
    if _UID_PATH_PARAMS & set(route.param_convertors):
        return True
    for body_param in route.dependant.body_params:
        fields = getattr(body_param.field_info.annotation, "model_fields", None)
        if fields and _UID_BODY_FIELDS & set(fields):
            return True
    return False


def _is_project_scoped(route: APIRoute) -> bool:
    return bool(_PROJECT_PATH_PARAMS & set(route.param_convertors))


def test_every_session_scoped_route_is_guarded() -> None:
    unguarded: list[tuple[str, str]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not _is_session_scoped(route):
            continue
        key = (sorted(route.methods)[0], route.path)
        if key in _EXEMPT:
            continue
        calls = {dep.call for dep in route.dependant.dependencies}
        if require_session_owner not in calls:
            unguarded.append(key)

    assert not unguarded, f"session-scoped routes missing the ownership guard: {unguarded}"


def test_every_project_scoped_route_is_guarded() -> None:
    """Same anti-fail-open check as above, for the `/projects` router.

    A brand new router (like `api/projects.py`) is exactly the hole
    `require_session_owner`'s router-level dependency can't close on its
    own -- this walks the live route table so a future project-scoped route
    added without the guard fails loudly here instead of silently trusting
    a caller-supplied `project_id`.
    """
    unguarded: list[tuple[str, str]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not _is_project_scoped(route):
            continue
        key = (sorted(route.methods)[0], route.path)
        calls = {dep.call for dep in route.dependant.dependencies}
        if require_project_owner not in calls:
            unguarded.append(key)

    assert not unguarded, f"project-scoped routes missing the ownership guard: {unguarded}"


def test_multipart_routes_never_resolve_uid_from_body() -> None:
    """Standing guard on the `Stream consumed` failure mode.

    `_resolve_session_uid` must never call `request.body()` on a multipart
    request -- reading it there raises, since `UploadFile` parsing drains the
    stream without caching it. Every multipart route must therefore carry its
    uid as a path param (resolved before any body touch), or be the one route
    that legitimately has no uid at all (`/images/upload`, which creates one).
    """
    offenders: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        has_upload_file = any(
            getattr(body_param.field_info.annotation, "__name__", "") == "UploadFile"
            for body_param in route.dependant.body_params
        )
        if not has_upload_file:
            continue
        if "uid" in route.param_convertors:
            continue
        if route.path.endswith("/upload") or route.path.startswith("/debug") or route.path == "/projects/import":
            # /images/upload creates the uid; every /debug/* route is a
            # standalone inspection tool with no session concept at all
            # (see "Debug vision endpoints" in CLAUDE.md). /projects/import
            # mints a brand-new project (and rooms under it) the same way --
            # it also lives on the /projects router, which never applies
            # require_session_owner in the first place (only
            # require_project_owner, which reads path params, not the body).
            continue
        offenders.append(route.path)

    assert not offenders, f"multipart routes with no path uid to guard on: {offenders}"
