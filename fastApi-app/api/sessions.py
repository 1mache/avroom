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

from core.image_codec import to_base64_ascii
from core.image_processing import debug_click_image_path
from core.auth.identity import current_user_id
from core.inference_pool.client import get_inference_client
from core.inference_pool.session_runtime import SessionConflictError
from core.mask_cache import delete_candidates
from core.repositories.job_repo import create_job, delete_job, get_job, list_session_jobs
from core.depth_cache import delete_session_depth_maps
from core.normal_cache import delete_session_normal_maps
from core.camera_calib_cache import delete_session_camera_calib
from core.object_metadata import list_object_ids
from schemas.batch import BatchRequest, BatchResponse
from schemas.image import ClickRequest, ClickResultResponse, SegmentRequest
from schemas.jobs import JobSubmitResponse, SubmitInpaintRequest
from schemas.sessions import (
    SessionInfo,
    SessionSyncCheckRequest,
    SessionSyncCheckResponse,
    SetNameRequest,
)
from core.object_storage import (
    current_background_path,
    legacy_object_cutout_path,
    legacy_object_glb_path,
    object_cutout_path,
    object_glb_path,
    remove_file,
    session_preview_path,
)
from core.cutout_bounds import extract_cutout_bounds_from_png_bytes
from core.repositories.session_repo import (
    SessionNotFoundError,
    delete_session as delete_session_row,
    evaluate_session_sync,
    is_session_registered,
    list_sessions_with_names,
    set_session_name,
    touch_session,
)
from settings import get_3d_storage_dir, get_image_storage_dir

router = APIRouter(prefix="/images", tags=["images"])
logger = logging.getLogger(__name__)


@router.get("/sessions")
async def get_sessions() -> list[SessionInfo]:
    """Return all image UIDs registered via upload, with optional human-readable names."""
    logger.info("Sessions list requested")
    result = [
        SessionInfo(uid=uid, name=name, last_changed=last_changed)
        for uid, name, last_changed in list_sessions_with_names()
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
    current_background_path(storage_dir, request.image_id).write_bytes(background_bytes)
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
        "Segmentation queued: image_id=%s x=%d y=%d verify=%s user_id=%s",
        request.image_id,
        request.x,
        request.y,
        request.verify.value,
        user_id,
    )
    payload = {
        "x": request.x,
        "y": request.y,
        "options": request.options.model_dump() if request.options else None,
        "verify": request.verify.value,
    }
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
        "Inpainting queued: image_id=%s mask_id=%s from_job_id=%s user_id=%s",
        request.image_id,
        request.mask_id,
        request.from_job_id,
        user_id,
    )
    job = create_job(user_id, request.image_id, "inpaint", {"mask_id": request.mask_id})

    if request.from_job_id is not None:
        source = get_job(user_id, request.from_job_id)
        if source is not None and source.kind == "segment":
            delete_job(request.from_job_id)

    return JobSubmitResponse(job_id=job.id)


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
    storage_dir = get_image_storage_dir()
    removed = 0

    try:
        # Snapshot object ids before the DB delete cascades them away.
        obj_ids = list_object_ids(uid)
        delete_session_row(uid)

        for path in storage_dir.glob(f"{uid}.*"):
            path.unlink(missing_ok=True)
            removed += 1

        three_d_dir = get_3d_storage_dir()
        for path in (
            current_background_path(storage_dir, uid),
            legacy_object_cutout_path(storage_dir, uid),
            session_preview_path(storage_dir, uid),
            debug_click_image_path(storage_dir, uid),
            # Legacy single GLB (written by earlier backend versions).
            legacy_object_glb_path(three_d_dir, uid),
        ):
            removed += remove_file(path)

        delete_candidates(storage_dir, uid)

        # Remove all numbered per-object cutouts and GLB files (metadata rows
        # already gone via the session-delete cascade above).
        for oid in obj_ids:
            removed += remove_file(object_cutout_path(storage_dir, uid, oid))
            removed += remove_file(object_glb_path(three_d_dir, uid, oid))

        removed += delete_session_depth_maps(storage_dir, uid)
        removed += delete_session_normal_maps(storage_dir, uid)
        removed += delete_session_camera_calib(storage_dir, uid)

        # Cached novel-view results and their preview placeholders, one file
        # per (object, snapped pose) pair -- glob rather than reconstructing
        # every possible filename.
        for path in storage_dir.glob(f"{uid}_*_novel_az*_el*.png"):
            path.unlink(missing_ok=True)
            removed += 1

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
