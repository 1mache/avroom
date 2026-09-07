"""Project lifecycle routes: list/create/rename/delete.

A project groups rooms (sessions) for one user. See CLAUDE.md's "Projects"
section for the hierarchy (`User -> Project -> Room`) and the cascade-delete
rationale.
"""

from __future__ import annotations

import logging
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from core.auth.identity import current_user_id
from core.auth.ownership import require_project_owner
from core.project_archive import (
    KIND_PROJECT,
    ArchiveFormatError,
    archive_filename,
    build_project_archive,
    restore_project_archive,
    restore_room_archive,
)
from core.repositories.project_repo import (
    ProjectNotFoundError,
    create_project,
    delete_project_row,
    get_project,
    list_project_session_ids,
    list_projects,
    set_project_name,
)
from core.repositories.session_repo import get_session_state
from core.session_teardown import delete_session_and_files
from schemas.projects import CreateProjectRequest, ProjectInfo, SetProjectNameRequest
from schemas.sessions import SessionInfo

router = APIRouter(prefix="/projects", tags=["projects"], dependencies=[Depends(require_project_owner)])
logger = logging.getLogger(__name__)


@router.get("")
async def get_projects(user_id: str = Depends(current_user_id)) -> list[ProjectInfo]:
    """Return the caller's projects, newest first."""
    logger.info("Projects list requested: user_id=%s", user_id)
    result = [
        ProjectInfo(
            id=summary.id,
            name=summary.name,
            room_count=summary.room_count,
            last_changed=summary.last_changed,
            preview_uid=summary.preview_uid,
        )
        for summary in list_projects(user_id)
    ]
    logger.info("Projects list returned: count=%d", len(result))
    return result


@router.post("", status_code=201)
async def create_project_endpoint(
    request: CreateProjectRequest, user_id: str = Depends(current_user_id)
) -> ProjectInfo:
    """Create a new, empty project. Returns 409 if the name is already taken."""
    logger.info("Project create requested: user_id=%s name=%r", user_id, request.name)
    try:
        project_id = create_project(user_id, request.name)
    except ValueError as exc:
        logger.warning("Project create rejected: user_id=%s name=%r reason=%s", user_id, request.name, exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    logger.info("Project created: id=%s user_id=%s", project_id, user_id)
    return ProjectInfo(id=project_id, name=request.name, room_count=0, last_changed=None, preview_uid=None)


@router.post("/import", status_code=201)
async def import_project_endpoint(
    file: UploadFile = File(...), user_id: str = Depends(current_user_id)
) -> ProjectInfo:
    """Recreate a project (fresh project/room/object ids) from a previously exported zip.

    Not project-scoped -- there's no `project_id` yet -- so `require_project_owner`
    passes through unchecked, same as `GET`/`POST /projects` today.
    """
    logger.info("Project import requested: user_id=%s filename=%r", user_id, file.filename)
    file_bytes = await file.read()

    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp_path = Path(tmp.name)
    try:
        tmp.write(file_bytes)
        tmp.close()
        try:
            project_id = restore_project_archive(tmp_path, user_id)
        except (ArchiveFormatError, zipfile.BadZipFile) as exc:
            logger.warning("Project import rejected: user_id=%s reason=%s", user_id, exc)
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    summary = get_project(project_id)
    assert summary is not None  # restore_project_archive above just created this row
    logger.info(
        "Project imported: project_id=%s user_id=%s rooms=%d", project_id, user_id, summary.room_count
    )
    return ProjectInfo(
        id=summary.id,
        name=summary.name,
        room_count=summary.room_count,
        last_changed=summary.last_changed,
        preview_uid=summary.preview_uid,
    )


@router.get("/{project_id}/export")
async def export_project_endpoint(project_id: str) -> FileResponse:
    """Download a project (every room, its metadata, and its blobs) as a zip."""
    summary = get_project(project_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Project not found for id='{project_id}'")
    logger.info("Project export requested: project_id=%s name=%r", project_id, summary.name)

    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp.close()
    out_path = Path(tmp.name)
    try:
        build_project_archive(project_id, out_path)
    except Exception:
        out_path.unlink(missing_ok=True)
        logger.exception("Project export failed: project_id=%s", project_id)
        raise

    logger.info("Project export ready: project_id=%s bytes=%d", project_id, out_path.stat().st_size)
    return FileResponse(
        out_path,
        media_type="application/zip",
        filename=archive_filename(summary.name, kind=KIND_PROJECT),
        background=BackgroundTask(out_path.unlink),
    )


@router.post("/{project_id}/rooms/import", status_code=201)
async def import_room_endpoint(
    project_id: str, file: UploadFile = File(...), user_id: str = Depends(current_user_id)
) -> SessionInfo:
    """Recreate a room (fresh room/object ids) inside *project_id* from a previously exported room zip.

    A room-name collision within the project auto-suffixes (`"<name>-copy"`,
    `-copy1`, ...) the same way a manual room copy does -- see
    `core.project_archive._restore_room`.
    """
    logger.info("Room import requested: project_id=%s user_id=%s filename=%r", project_id, user_id, file.filename)
    if get_project(project_id) is None:
        raise HTTPException(status_code=404, detail=f"Project not found for id='{project_id}'")

    file_bytes = await file.read()
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp_path = Path(tmp.name)
    try:
        tmp.write(file_bytes)
        tmp.close()
        try:
            new_uid = restore_room_archive(tmp_path, user_id, project_id)
        except (ArchiveFormatError, zipfile.BadZipFile) as exc:
            logger.warning("Room import rejected: project_id=%s reason=%s", project_id, exc)
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    state = get_session_state(new_uid)
    assert state is not None  # restore_room_archive above just created this row
    logger.info("Room imported: uid=%s project_id=%s name=%r", new_uid, project_id, state.name)
    return SessionInfo(uid=new_uid, name=state.name, last_changed=state.last_changed)


@router.post("/{project_id}/name")
async def set_project_name_endpoint(project_id: str, request: SetProjectNameRequest) -> ProjectInfo:
    """Rename a project. Returns 409 if the name is already taken by another of the caller's projects."""
    logger.info("Project rename requested: project_id=%s name=%r", project_id, request.name)
    try:
        set_project_name(project_id, request.name)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project not found for id='{project_id}'") from None
    except ValueError as exc:
        logger.warning("Project rename rejected: project_id=%s name=%r reason=%s", project_id, request.name, exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    logger.info("Project renamed: project_id=%s name=%r", project_id, request.name)
    summary = get_project(project_id)
    assert summary is not None  # set_project_name above already proved the row exists
    return ProjectInfo(
        id=summary.id,
        name=summary.name,
        room_count=summary.room_count,
        last_changed=summary.last_changed,
        preview_uid=summary.preview_uid,
    )


@router.delete("/{project_id}", status_code=204)
async def delete_project_endpoint(project_id: str) -> None:
    """Permanently delete a project and every room inside it.

    Loops the same per-room teardown `DELETE /images/{uid}` uses
    (`core.session_teardown.delete_session_and_files`) so no room's blobs
    (cutouts, GLBs, novel-view caches) are left behind on disk, then deletes
    the now-empty project row.
    """
    session_ids = list_project_session_ids(project_id)
    logger.info("Project delete requested: project_id=%s rooms=%d", project_id, len(session_ids))
    for session_id in session_ids:
        delete_session_and_files(session_id)
    delete_project_row(project_id)
    logger.info("Project deleted: project_id=%s rooms_removed=%d", project_id, len(session_ids))
