"""Session lifecycle and pipeline-submission routes.

Covers session listing/deletion/naming/sync, the legacy single-shot click
endpoint, segment/inpaint job submission, and batch processing — everything
that operates on a session (or the whole session list) rather than on one
already-finalized object. See ``api/routes.py`` for upload plus the object
CRUD/rescale endpoints, and ``api/object_views.py`` for read-only artifact
serving; all three routers share the ``/images`` prefix and are mounted
together in ``main.py``.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from pathlib import Path

from core.session_teardown import delete_session_and_files

from core.image_codec import to_base64_ascii
from core.image_processing import (
    canvas_shape_from_bytes,
    decode_erase_mask_png,
    load_canvas_bytes,
    split_mask_components,
)
from core.auth.identity import current_user_id
from core.auth.ownership import require_session_owner
from core.inference_pool.client import get_inference_client
from core.inference_pool.session_runtime import SessionConflictError, acquire_canvas_writer, release_canvas_writer
from core.mask_cache import save_refined_mask_only
from core.repositories.job_repo import create_job, delete_job, get_job, list_session_jobs
from schemas.batch import BatchRequest, BatchResponse
from schemas.image import ClickRequest, ClickResultResponse, SegmentRequest
from schemas.jobs import JobSubmitResponse, SubmitEraseRequest, SubmitInpaintRequest
from schemas.sessions import (
    SessionInfo,
    SessionSyncCheckRequest,
    SessionSyncCheckResponse,
    SetNameRequest,
)
from core.object_storage import legacy_object_cutout_path
from core.cutout_bounds import extract_cutout_bounds_from_png_bytes
from core.repositories.session_repo import (
    SessionNotFoundError,
    evaluate_session_sync,
    is_session_registered,
    list_sessions_with_names,
    set_session_name,
    touch_session,
)
from core.session_history import (
    HistoryBoundaryError,
    HistoryConflictError,
    commit_background,
    redo_background,
    undo_background,
)
from settings import get_image_storage_dir

router = APIRouter(prefix="/images", tags=["images"], dependencies=[Depends(require_session_owner)])
logger = logging.getLogger(__name__)


@router.get("/sessions")
async def get_sessions(
    project_id: str | None = None, user_id: str = Depends(current_user_id)
) -> list[SessionInfo]:
    """Return the caller's rooms, with optional human-readable names.

    `project_id`, when given, scopes the list to one project's rooms (the
    Rooms dashboard's normal case); omitted, every room the caller owns is
    returned regardless of project.
    """
    logger.info("Sessions list requested: user_id=%s project_id=%s", user_id, project_id)
    result = [
        SessionInfo(uid=uid, name=name, last_changed=last_changed)
        for uid, name, last_changed in list_sessions_with_names(user_id, project_id)
    ]
    logger.info("Sessions list returned: count=%d", len(result))
    return result


@router.post("/click", response_model=ClickResultResponse)
def handle_click(request: ClickRequest) -> ClickResultResponse:
    """Handle a user's click on a previously uploaded image.

    The coordinates are expressed in pixels with origin at the top-left of the image.
    This endpoint loads the stored image, performs segmentation based on
    the click, and returns background and cutout images as base64-encoded strings.
    """

    logger.info(
        "Click received: image_id=%s x=%d y=%d",
        request.image_id,
        request.x,
        request.y,
    )

    storage_dir: Path = get_image_storage_dir()

    try:
        background_bytes, cutout_bytes, image_format = get_inference_client().run_click(
            image_id=request.image_id,
            base_dir=storage_dir,
            x=request.x,
            y=request.y,
            options=request.options,
        )
    except ValueError as exc:
        logger.exception("Click processing failed due to invalid input")
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        logger.exception("Click processing failed due to missing file")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Click processing failed")
        raise HTTPException(status_code=500, detail=f"Click processing failed: {exc}") from exc

    # Legacy endpoint: writes the pre-numbering artifact names, which
    # resolve_object_cutout_path still reads back as object id 0.
    commit_background(request.image_id, background_bytes, storage_dir)
    legacy_object_cutout_path(storage_dir, request.image_id).write_bytes(cutout_bytes)
    touch_session(request.image_id)

    background_b64 = to_base64_ascii(background_bytes)
    cutout_b64 = to_base64_ascii(cutout_bytes)
    # Frontend uses these bounds to clamp drag by visible object, not by the
    # transparent padding that exists around most cutouts.
    cutout_bounds = extract_cutout_bounds_from_png_bytes(cutout_bytes)

    logger.info(
        "Click processed: image_id=%s background_bytes=%d cutout_bytes=%d format=%s",
        request.image_id,
        len(background_bytes),
        len(cutout_bytes),
        image_format,
    )

    return ClickResultResponse(
        image_id=request.image_id,
        background_b64=background_b64,
        cutout_b64=cutout_b64,
        format=image_format,
        cutout_bounds=cutout_bounds,
    )


@router.post("/segment", response_model=JobSubmitResponse, status_code=202)
async def segment_image(
    request: SegmentRequest, user_id: str = Depends(current_user_id)
) -> JobSubmitResponse:
    """Queue segmentation for a click and return immediately.

    The actual work (and any 409-equivalent conflict against an in-flight
    inpaint's region) is resolved when the dispatcher claims the job — see
    `core/jobs/handlers.py::run_segment_job`. Poll `GET /jobs/{job_id}` (or
    `POST /images/{uid}/sync-check`, which now embeds the session's jobs) for
    the result.
    """
    logger.info(
        "Segmentation queued: image_id=%s x=%d y=%d points=%d verify=%s user_id=%s",
        request.image_id,
        request.x,
        request.y,
        len(request.points) if request.points else 1,
        request.verify.value,
        user_id,
    )
    payload: dict[str, object] = {
        "x": request.x,
        "y": request.y,
        "options": request.options.model_dump() if request.options else None,
        "verify": request.verify.value,
    }
    if request.points is not None:
        payload["points"] = [{"x": point.x, "y": point.y} for point in request.points]
    job = create_job(user_id, request.image_id, "segment", payload)
    return JobSubmitResponse(job_id=job.id)


@router.post("/inpaint", response_model=JobSubmitResponse, status_code=202)
async def inpaint_mask(
    request: SubmitInpaintRequest, user_id: str = Depends(current_user_id)
) -> JobSubmitResponse:
    """Queue inpainting of one selected cached mask candidate and return immediately.

    If `from_job_id` names the segment job this mask came from, that job's
    row is consumed here (removed from the picker backlog) — the mask id
    stays protected from a concurrent segment's candidate wipe because this
    new inpaint job is now itself in `reserved_mask_ids` until it runs.
    """
    logger.info(
        "Inpainting queued: image_id=%s mask_id=%s from_job_id=%s generate_3d=%s user_id=%s",
        request.image_id,
        request.mask_id,
        request.from_job_id,
        request.generate_3d,
        user_id,
    )
    job = create_job(
        user_id,
        request.image_id,
        "inpaint",
        {"mask_id": request.mask_id, "generate_3d": request.generate_3d},
    )

    if request.from_job_id is not None:
        source = get_job(user_id, request.from_job_id)
        if source is not None and source.kind == "segment":
            delete_job(request.from_job_id)

    return JobSubmitResponse(job_id=job.id)


@router.post("/erase", response_model=JobSubmitResponse, status_code=202)
async def erase_region(
    request: SubmitEraseRequest, user_id: str = Depends(current_user_id)
) -> JobSubmitResponse:
    """Queue erasure of client-drawn mask region(s) and return immediately.

    The submitted mask may contain several disconnected blobs (e.g. chair +
    table lassoed with Shift). Each blob becomes its own durable erase job so
    later jobs inpaint against the canvas the earlier ones already wrote.
    """
    if not is_session_registered(request.image_id):
        raise HTTPException(status_code=404, detail=f"Unknown session uid={request.image_id}")

    storage_dir = get_image_storage_dir()
    try:
        canvas_bytes = load_canvas_bytes(image_id=request.image_id, base_dir=storage_dir)
        expected_shape = canvas_shape_from_bytes(canvas_bytes)
        mask = decode_erase_mask_png(request.mask_b64, expected_shape)
        components = split_mask_components(mask)
    except ValueError as exc:
        logger.warning("Erase rejected: image_id=%s reason=%s", request.image_id, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    job_ids: list[str] = []
    for component in components:
        job = create_job(user_id, request.image_id, "erase", {})
        save_refined_mask_only(storage_dir, request.image_id, job.id, component)
        job_ids.append(job.id)

    logger.info(
        "Erase queued: image_id=%s blobs=%d first_job_id=%s user_id=%s",
        request.image_id,
        len(job_ids),
        job_ids[0],
        user_id,
    )
    return JobSubmitResponse(job_id=job_ids[0])


@router.post("/{uid}/batch", response_model=BatchResponse)
def run_batch(uid: str, request: BatchRequest) -> BatchResponse:
    """Discover or select objects, peel with auto verify, then generate GLBs."""

    logger.info("Batch requested: uid=%s source=%s", uid, request.source.kind)
    if not is_session_registered(uid):
        raise HTTPException(status_code=404, detail=f"Unknown session uid={uid}")
    from core.batch_jobs import run_session_batch

    try:
        result = run_session_batch(uid, request, get_image_storage_dir())
    except SessionConflictError as exc:
        logger.warning("Batch rejected due to session conflict: %s", exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        logger.exception("Batch failed due to missing file")
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        logger.exception("Batch failed due to invalid input")
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Batch failed")
        raise HTTPException(status_code=500, detail=f"Batch failed: {exc}") from exc
    logger.info("Batch finished: uid=%s batch_id=%s", uid, result.batch_id)
    return result


@router.delete("/{uid}", status_code=204)
async def delete_session(uid: str) -> Response:
    """Delete a session and all its associated files from disk.

    Deletes the session's DB row (cascading to every object row under it) and
    every file associated with that uid: the original uploaded image,
    processed background and cutout PNGs, candidate mask files, debug
    overlay, and any cached 3D model. Missing files are silently ignored so
    the endpoint is safe to call more than once.
    """
    logger.info("Session delete requested: uid=%s", uid)
    try:
        removed = delete_session_and_files(uid)
    except Exception as exc:
        logger.error("Session delete failed: uid=%s error=%s", uid, exc)
        raise HTTPException(status_code=500, detail=f"Session delete failed: {exc}") from exc

    logger.info("Session deleted: uid=%s files_removed=%d", uid, removed)
    return Response(status_code=204)


@router.post("/{uid}/name", response_model=SessionInfo)
async def set_name(uid: str, request: SetNameRequest) -> SessionInfo:
    """Assign a human-readable name to a session.

    Names are unique across all sessions.  Returns 409 if the name is already
    taken by a different session.
    """
    logger.info("Set name requested: uid=%s name=%r", uid, request.name)
    try:
        set_session_name(uid, request.name)
    except ValueError as exc:
        logger.error("Name conflict: uid=%s name=%r reason=%s", uid, request.name, exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    last_changed = touch_session(uid)
    logger.info("Name set: uid=%s name=%r", uid, request.name)
    return SessionInfo(uid=uid, name=request.name, last_changed=last_changed)


def _run_history_step(uid: str, *, undo: bool) -> Response:
    """Shared body for undo/redo: canvas-writer lock, history step, touch."""

    storage_dir = get_image_storage_dir()
    action = "undo" if undo else "redo"
    logger.info("Background %s requested: uid=%s", action, uid)
    try:
        try:
            acquire_canvas_writer(uid)
        except SessionConflictError as exc:
            logger.warning("Background %s rejected — canvas writer timeout: uid=%s", action, uid)
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        try:
            if undo:
                undo_background(uid, storage_dir)
            else:
                redo_background(uid, storage_dir)
            touch_session(uid)
        finally:
            release_canvas_writer(uid)
    except SessionNotFoundError:
        logger.warning("Background %s failed — unknown uid: %s", action, uid)
        raise HTTPException(status_code=404, detail=f"Session not found for uid='{uid}'") from None
    except HistoryConflictError as exc:
        logger.warning("Background %s rejected — active jobs: uid=%s", action, uid)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HistoryBoundaryError as exc:
        logger.warning("Background %s rejected — boundary: uid=%s", action, uid)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Background %s failed: uid=%s", action, uid)
        raise HTTPException(status_code=500, detail=f"Background {action} failed: {exc}") from exc

    logger.info("Background %s complete: uid=%s", action, uid)
    return Response(status_code=204)


@router.post("/{uid}/history/undo", status_code=204)
def undo_session_background(uid: str) -> Response:
    """Restore the previous background stage (and hide later objects)."""

    return _run_history_step(uid, undo=True)


@router.post("/{uid}/history/redo", status_code=204)
def redo_session_background(uid: str) -> Response:
    """Move one stage forward on the background history stack."""

    return _run_history_step(uid, undo=False)


@router.post("/{uid}/sync-check", response_model=SessionSyncCheckResponse)
async def sync_check_session(
    uid: str, request: SessionSyncCheckRequest, user_id: str = Depends(current_user_id)
) -> SessionSyncCheckResponse:
    """Compare a client-held session timestamp against server truth.

    Also returns this session's jobs (queued/running/done/failed/conflict) —
    the polling channel the frontend uses to notice queued work has landed,
    since this endpoint is already polled every ~2s while work is pending.
    """
    logger.debug(
        "Session sync-check requested: uid=%s client_last_changed=%r",
        uid,
        request.client_last_changed,
    )
    try:
        server_last_changed, needs_refresh = evaluate_session_sync(
            uid,
            request.client_last_changed,
        )
    except SessionNotFoundError:
        logger.warning("Session sync-check failed — unknown uid: %s", uid)
        raise HTTPException(status_code=404, detail=f"Session not found for uid='{uid}'") from None
    if needs_refresh:
        logger.info(
            "Session sync-check mismatch: uid=%s last_changed=%r",
            uid,
            server_last_changed,
        )
    else:
        logger.debug(
            "Session sync-check match: uid=%s last_changed=%r",
            uid,
            server_last_changed,
        )
    jobs = list_session_jobs(user_id, uid)
    return SessionSyncCheckResponse(
        last_changed=server_last_changed,
        needs_refresh=needs_refresh,
        jobs=jobs,
    )
