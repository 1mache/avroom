from __future__ import annotations

from typing import Annotated

import uuid
import logging
import base64

import json
import cv2
import numpy as np

from fastapi import APIRouter, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pathlib import Path

from core.image_processing import (
    build_object_metadata_for_inpaint,
    get_image_path,
)
from core.image_validation import ImageValidationError, ImageValidator
from core.inference_pool.client import get_inference_client
from core.inference_pool.session_runtime import (
    SessionConflictError,
    acquire_canvas_writer,
    assert_segment_click_allowed,
    drop_lease,
    pinned_mask_ids,
    release_canvas_writer,
    try_admit_inpaint,
)
from core.mask_cache import delete_candidate, delete_candidates
from core.depth_cache import delete_session_depth_maps
from core.object_metadata import (
    ObjectMetadata,
    get_object_by_uuid,
    load_object_metadata,
    save_object_metadata,
    set_object_name,
    delete_session_metadata,
)
from schemas.image import (
    ClickRequest,
    ClickResultResponse,
    CutoutBounds,
    ImageUploadResponse,
    InpaintMaskRequest,
    InpaintMaskResponse,
    ObjectInfo,
    ObjectListResponse,
    ObjectMetadataResponse,
    SegmentMaskOption,
    SegmentRequest,
    SegmentResponse,
    SessionInfo,
    SessionSyncCheckRequest,
    SessionSyncCheckResponse,
    SetNameRequest,
    SetObjectNameRequest,
    RescaleByDepthRequest,
    RescaleByDepthResponse,
    UidCacheStatusResponse,
)
from core.object_storage import (
    current_background_path,
    list_object_ids,
    next_object_id,
    object_cutout_path,
    object_glb_path,
    resolve_object_cutout_path,
    resolve_object_glb_path,
)
from core.cutout_bounds import extract_cutout_bounds_from_png_bytes
from settings import (
    clear_session_last_changed,
    deregister_uid,
    get_3d_storage_dir,
    get_image_storage_dir,
    get_session_last_changed,
    get_sessions_file,
    evaluate_session_sync,
    load_names,
    register_uid,
    remove_session_name,
    SessionNotFoundError,
    set_session_name,
    touch_session,
)

router = APIRouter(prefix="/images", tags=["images"])
logger = logging.getLogger(__name__)


@router.get("/sessions")
async def get_sessions() -> list[SessionInfo]:
    """Return all image UIDs registered via upload, with optional human-readable names."""
    logger.info("Sessions list requested")
    sessions_file = get_sessions_file()
    uids: list[str] = []
    if sessions_file.exists():
        try:
            uids = json.loads(sessions_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            uids = []

    names = load_names()
    result = [
        SessionInfo(uid=u, name=names.get(u), last_changed=get_session_last_changed(u))
        for u in uids
    ]
    logger.info("Sessions list returned: count=%d", len(result))
    return result


@router.post("/upload", response_model=ImageUploadResponse)
async def upload_image(
    file: Annotated[UploadFile, File(..., description="Image file to be stored on the server.")],
) -> ImageUploadResponse:
    """Upload an image and persist it to disk.

    The server assigns a new `image_id` and saves the file under the configured
    image storage directory. The returned `image_id` is later used by the click
    endpoint to reference this stored image.
    """

    logger.info(
        "Upload received: filename=%s content_type=%s",
        file.filename,
        file.content_type,
    )

    storage_dir: Path = get_image_storage_dir()
    storage_dir.mkdir(parents=True, exist_ok=True)

    image_id = str(uuid.uuid4())
    original_filename: str | None = file.filename or None

    # Determine a simple extension; for now default to .png if unknown.
    suffix = ".png"
    if original_filename and "." in original_filename:
        suffix = "." + original_filename.rsplit(".", 1)[1].lower()

    image_path = storage_dir / f"{image_id}{suffix}"
    try:
        file_bytes = await file.read()
    except Exception as exc:
        logger.exception("Upload read failed: image_id=%s", image_id)
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc

    try:
        ImageValidator().validate(
            file_bytes,
            filename=original_filename,
            content_type=file.content_type,
        )
    except ImageValidationError as exc:
        logger.warning(
            "Upload rejected by technical validation: filename=%s detail=%s",
            original_filename,
            exc,
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        logger.warning(
            "Upload rejected by technical validation: filename=%s detail=%s",
            original_filename,
            exc,
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    content_outcome = get_inference_client().run_validate_content(image_bytes=file_bytes)
    if not content_outcome.is_valid:
        detail = "; ".join(content_outcome.messages) or "Image failed content validation."
        logger.warning(
            "Upload rejected by content validation: filename=%s checks=%s",
            original_filename,
            {name: passed for name, passed in content_outcome.checks.items() if not passed},
        )
        raise HTTPException(status_code=422, detail=detail)

    try:
        image_path.write_bytes(file_bytes)
    except Exception as exc:
        logger.exception("Upload failed: image_id=%s", image_id)
        raise HTTPException(status_code=500, detail=f"Upload failed: {exc}") from exc

    logger.info(
        "Upload stored: image_id=%s path=%s size_bytes=%d",
        image_id,
        image_path,
        len(file_bytes),
    )

    register_uid(image_id)
    last_changed = touch_session(image_id)

    return ImageUploadResponse(
        image_id=image_id,
        original_filename=original_filename,
        stored_path=str(image_path),
        last_changed=last_changed,
    )


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

    # save the background and cutout images to the disk
    background_image_path = storage_dir / f"{request.image_id}_background.png"
    background_image_path.write_bytes(background_bytes)
    cutout_image_path = storage_dir / f"{request.image_id}_cutout.png"
    cutout_image_path.write_bytes(cutout_bytes)
    touch_session(request.image_id)

    background_b64 = base64.b64encode(background_bytes).decode("ascii")
    cutout_b64 = base64.b64encode(cutout_bytes).decode("ascii")
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


@router.post("/segment", response_model=SegmentResponse)
def segment_image(request: SegmentRequest) -> SegmentResponse:
    """Return all mask candidates for a click without running inpainting."""

    logger.info(
        "Segmentation requested: image_id=%s x=%d y=%d",
        request.image_id,
        request.x,
        request.y,
    )

    storage_dir: Path = get_image_storage_dir()

    try:
        assert_segment_click_allowed(request.image_id, request.x, request.y)
        candidates = get_inference_client().run_segment(
            image_id=request.image_id,
            base_dir=storage_dir,
            x=request.x,
            y=request.y,
            options=request.options,
            exclude_mask_ids=frozenset(pinned_mask_ids(request.image_id)),
        )
    except SessionConflictError as exc:
        logger.warning("Segmentation rejected due to session conflict: %s", exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        logger.exception("Segmentation failed due to invalid input")
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        logger.exception("Segmentation failed due to missing file")
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Segmentation failed")
        raise HTTPException(status_code=500, detail=f"Segmentation failed: {exc}") from exc

    masks: list[SegmentMaskOption] = []
    for mask_id, cutout_bytes in candidates:
        # Frontend previews object pixels directly. Raw refined masks stay
        # server-side because they are model inputs, not user-facing images.
        masks.append(
            SegmentMaskOption(
                mask_id=mask_id,
                cutout_b64=base64.b64encode(cutout_bytes).decode("ascii"),
                format="png",
                cutout_bounds=extract_cutout_bounds_from_png_bytes(cutout_bytes),
            )
        )

    logger.info(
        "Segmentation complete: image_id=%s candidates=%d",
        request.image_id,
        len(masks),
    )
    return SegmentResponse(image_id=request.image_id, masks=masks)


@router.post("/inpaint", response_model=InpaintMaskResponse)
def inpaint_mask(request: InpaintMaskRequest) -> InpaintMaskResponse:
    """Inpaint background using one user-selected cached mask candidate."""

    logger.info(
        "Inpainting requested: image_id=%s mask_id=%s",
        request.image_id,
        request.mask_id,
    )

    storage_dir: Path = get_image_storage_dir()
    lease = None

    try:
        lease = try_admit_inpaint(request.image_id, request.mask_id, storage_dir)
    except FileNotFoundError as exc:
        logger.exception("Inpainting failed due to missing cached mask or image")
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SessionConflictError as exc:
        logger.warning("Inpainting rejected due to session conflict: %s", exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        try:
            acquire_canvas_writer(request.image_id)
        except SessionConflictError as exc:
            logger.warning("Inpainting rejected due to canvas writer timeout: %s", exc)
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        try:
            background_bytes, cutout_bytes, image_format = get_inference_client().run_inpaint(
                image_id=request.image_id,
                mask_id=request.mask_id,
                base_dir=storage_dir,
            )
        except FileNotFoundError as exc:
            logger.exception("Inpainting failed due to missing cached mask or image")
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            logger.exception("Inpainting failed due to invalid input")
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Inpainting failed")
            raise HTTPException(status_code=500, detail=f"Inpainting failed: {exc}") from exc

        # Allocate next sequential object id for this session.
        object_id = next_object_id(storage_dir, request.image_id)

        object_metadata = build_object_metadata_for_inpaint(
            image_id=request.image_id,
            mask_id=request.mask_id,
            object_id=object_id,
            base_dir=storage_dir,
        )
        save_object_metadata(storage_dir, object_metadata)

        # Background always written to the single cumulative canvas path (overwrites → becomes new canvas).
        background_image_path = current_background_path(storage_dir, request.image_id)
        background_image_path.write_bytes(background_bytes)

        # Cutout written to the per-object numbered path (never overwrites a prior object).
        cutout_image_path = object_cutout_path(storage_dir, request.image_id, object_id)
        cutout_image_path.write_bytes(cutout_bytes)

        # Selected candidate is promoted; remove only that mask's temp files.
        delete_candidate(storage_dir, request.image_id, request.mask_id)
        touch_session(request.image_id)
    finally:
        if lease is not None:
            drop_lease(request.image_id, lease)
        release_canvas_writer(request.image_id)

    background_b64 = base64.b64encode(background_bytes).decode("ascii")
    cutout_b64 = base64.b64encode(cutout_bytes).decode("ascii")
    cutout_bounds = extract_cutout_bounds_from_png_bytes(cutout_bytes)

    logger.info(
        "Inpainting complete: image_id=%s mask_id=%s background_bytes=%d cutout_bytes=%d object_id=%d object_uuid=%s",
        request.image_id,
        request.mask_id,
        len(background_bytes),
        len(cutout_bytes),
        object_id,
        object_metadata.uuid,
    )

    return InpaintMaskResponse(
        image_id=request.image_id,
        background_b64=background_b64,
        cutout_b64=cutout_b64,
        format=image_format,
        cutout_bounds=cutout_bounds,
        object_id=object_id,
        object_uuid=object_metadata.uuid,
    )


@router.delete("/{uid}", status_code=204)
async def delete_session(uid: str) -> Response:
    """Delete a session and all its associated files from disk.

    Removes the uid from sessions.json, removes its name from names.json if
    present, and deletes every file associated with that uid: the original
    uploaded image, processed background and cutout PNGs, candidate mask
    files, debug overlay, and any cached 3D model.  Missing files are
    silently ignored so the endpoint is safe to call more than once.
    """
    logger.info("Session delete requested: uid=%s", uid)
    storage_dir = get_image_storage_dir()
    removed = 0

    try:
        deregister_uid(uid)
        remove_session_name(uid)
        clear_session_last_changed(uid)

        for path in storage_dir.glob(f"{uid}.*"):
            path.unlink(missing_ok=True)
            removed += 1

        for suffix in ("_background.png", "_cutout.png"):
            p = storage_dir / f"{uid}{suffix}"
            if p.exists():
                p.unlink()
                removed += 1

        delete_candidates(storage_dir, uid)

        # Collect per-object ids before deleting files (list_object_ids scans disk).
        obj_ids = list_object_ids(storage_dir, uid)

        # Remove all numbered per-object cutouts.
        for oid in obj_ids:
            p = object_cutout_path(storage_dir, uid, oid)
            if p.exists():
                p.unlink()
                removed += 1

        delete_session_metadata(storage_dir, uid, obj_ids)
        removed += delete_session_depth_maps(storage_dir, uid)

        debug_path = storage_dir / "point" / f"{uid}_debug.png"
        if debug_path.exists():
            debug_path.unlink()
            removed += 1

        # Legacy single GLB (written by earlier backend versions).
        glb_path = get_3d_storage_dir() / f"{uid}.glb"
        if glb_path.exists():
            glb_path.unlink()
            removed += 1

        # Remove all numbered per-object GLB files.
        three_d_dir = get_3d_storage_dir()
        for oid in obj_ids:
            p = object_glb_path(three_d_dir, uid, oid)
            if p.exists():
                p.unlink()
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
async def sync_check_session(uid: str, request: SessionSyncCheckRequest) -> SessionSyncCheckResponse:
    """Compare a client-held session timestamp against server truth."""
    logger.info(
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
    logger.info(
        "Session sync-check complete: uid=%s needs_refresh=%s last_changed=%r",
        uid,
        needs_refresh,
        server_last_changed,
    )
    return SessionSyncCheckResponse(
        last_changed=server_last_changed,
        needs_refresh=needs_refresh,
    )


def _metadata_to_response(
    metadata: ObjectMetadata,
    storage_dir: Path,
    three_d_dir: Path,
) -> ObjectMetadataResponse:
    """Build API response from stored metadata plus derived artifact flags."""
    cutout_path = resolve_object_cutout_path(storage_dir, metadata.session_id, metadata.object_id)
    cutout_bounds = None
    if cutout_path.exists():
        cutout_bounds = extract_cutout_bounds_from_png_bytes(cutout_path.read_bytes())
    has_3d = resolve_object_glb_path(three_d_dir, metadata.session_id, metadata.object_id).exists()
    return ObjectMetadataResponse(
        uuid=metadata.uuid,
        session_id=metadata.session_id,
        object_id=metadata.object_id,
        name=metadata.name,
        average_depth=metadata.average_depth,
        content_hash=metadata.content_hash,
        created_at=metadata.created_at,
        has_3d=has_3d,
        cutout_bounds=cutout_bounds,
    )


@router.get("/objects/{object_uuid}", response_model=ObjectMetadataResponse)
async def get_object_by_uuid_endpoint(object_uuid: str) -> ObjectMetadataResponse:
    """Return metadata for one object searchable by its UUID."""
    logger.info("Object metadata requested: uuid=%s", object_uuid)
    storage_dir = get_image_storage_dir()
    metadata = get_object_by_uuid(storage_dir, object_uuid)
    if metadata is None:
        logger.warning("Object metadata not found: uuid=%s", object_uuid)
        raise HTTPException(status_code=404, detail=f"Object not found for uuid='{object_uuid}'")
    response = _metadata_to_response(metadata, storage_dir, get_3d_storage_dir())
    logger.info(
        "Object metadata returned: uuid=%s session_id=%s object_id=%d",
        object_uuid,
        metadata.session_id,
        metadata.object_id,
    )
    return response


@router.patch("/objects/{object_uuid}", response_model=ObjectMetadataResponse)
async def rename_object(object_uuid: str, request: SetObjectNameRequest) -> ObjectMetadataResponse:
    """Update the optional name on one object identified by UUID."""
    logger.info("Object rename requested: uuid=%s name=%r", object_uuid, request.name)
    storage_dir = get_image_storage_dir()
    try:
        metadata = set_object_name(storage_dir, object_uuid, request.name)
    except FileNotFoundError as exc:
        logger.warning("Object rename failed — not found: uuid=%s", object_uuid)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    touch_session(metadata.session_id)
    response = _metadata_to_response(metadata, storage_dir, get_3d_storage_dir())
    logger.info("Object renamed: uuid=%s name=%r", object_uuid, request.name)
    return response


@router.post("/objects/{object_uuid}/rescale-by-depth", response_model=RescaleByDepthResponse)
def rescale_object_by_depth(
    object_uuid: str,
    request: RescaleByDepthRequest,
) -> RescaleByDepthResponse:
    """Rescale a cutout proportionally based on depth at the given placement point."""
    logger.info(
        "Rescale by depth requested: uuid=%s placement=(%d,%d)",
        object_uuid,
        request.x,
        request.y,
    )
    storage_dir = get_image_storage_dir()
    try:
        result = get_inference_client().run_rescale_by_depth(
            base_dir=storage_dir,
            object_uuid=object_uuid,
            x=request.x,
            y=request.y,
        )
    except FileNotFoundError as exc:
        logger.warning("Rescale by depth failed — not found: uuid=%s", object_uuid)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        logger.error("Rescale by depth failed — invalid input: uuid=%s reason=%s", object_uuid, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    touch_session(result.session_id)
    cutout_bounds = extract_cutout_bounds_from_png_bytes(result.cutout_bytes)
    logger.info(
        "Rescale by depth complete: uuid=%s scale_factor=%.4f target_depth=%.2f",
        object_uuid,
        result.scale_factor,
        result.target_depth,
    )
    return RescaleByDepthResponse(
        object_uuid=result.object_uuid,
        session_id=result.session_id,
        object_id=result.object_id,
        source_average_depth=result.source_average_depth,
        target_depth=result.target_depth,
        scale_factor=result.scale_factor,
        cutout_b64=base64.b64encode(result.cutout_bytes).decode("ascii"),
        format="png",
        cutout_bounds=cutout_bounds,
    )


@router.get("/{uid}/objects", response_model=ObjectListResponse)
async def get_session_objects(uid: str) -> ObjectListResponse:
    """Return all processed objects for a session with cutout thumbnails.

    Scans the storage directory for finalized per-object cutout PNGs and
    returns them as base64 thumbnails alongside their tight alpha bounds and
    a flag indicating whether a GLB 3D model has been generated.
    """
    logger.info("Objects list requested: uid=%s", uid)
    storage_dir = get_image_storage_dir()
    # TODO: validate uid against sessions.json and return 404 for unknown sessions.
    # Currently returns 200 + empty list for unknown UIDs, consistent with /{uid}/cache.
    obj_ids = list_object_ids(storage_dir, uid)
    three_d_dir = get_3d_storage_dir()

    # TODO: this loop performs blocking I/O per object synchronously on the async event loop.
    # For MVP session sizes this is acceptable; move to a thread pool executor if sessions
    # grow to many large objects.
    objects_list: list[ObjectInfo] = []
    for oid in obj_ids:
        try:
            cutout_path = resolve_object_cutout_path(storage_dir, uid, oid)
            if not cutout_path.exists():
                logger.warning(
                    "Objects list: cutout missing for uid=%s object_id=%d path=%s — skipping",
                    uid,
                    oid,
                    cutout_path,
                )
                continue
            cutout_bytes = cutout_path.read_bytes()
            cutout_b64 = base64.b64encode(cutout_bytes).decode("ascii")
            cutout_bounds = extract_cutout_bounds_from_png_bytes(cutout_bytes)
            has_3d = resolve_object_glb_path(three_d_dir, uid, oid).exists()
            meta = load_object_metadata(storage_dir, uid, oid)
            objects_list.append(
                ObjectInfo(
                    object_id=oid,
                    uuid=meta.uuid if meta is not None else None,
                    name=meta.name if meta is not None else None,
                    average_depth=meta.average_depth if meta is not None else None,
                    cutout_b64=cutout_b64,
                    format="png",
                    cutout_bounds=cutout_bounds,
                    has_3d=has_3d,
                )
            )
        except FileNotFoundError as exc:
            logger.warning(
                "Objects list: file not found for uid=%s object_id=%d error=%s — skipping",
                uid,
                oid,
                exc,
            )

    logger.info("Objects list returned: uid=%s count=%d", uid, len(objects_list))
    return ObjectListResponse(uid=uid, objects=objects_list)


@router.get("/{uid}/cache", response_model=UidCacheStatusResponse)
async def get_uid_cache_status(uid: str) -> UidCacheStatusResponse:
    """Return which processed artifacts are cached on disk for the given UID."""
    logger.info("Cache status requested: uid=%s", uid)
    storage_dir = get_image_storage_dir()
    obj_ids = list_object_ids(storage_dir, uid)

    # Derive cutout bounds from the latest (highest-id) object.
    latest_object_id = max(obj_ids) if obj_ids else None
    cutout_path_to_check = (
        resolve_object_cutout_path(storage_dir, uid, latest_object_id)
        if latest_object_id is not None
        else None
    )
    cutout_bounds = None
    if cutout_path_to_check is not None and cutout_path_to_check.exists():
        # Session restore should not need to re-run segmentation just to recover
        # drag bounds, so cache metadata derives from stored PNG on demand.
        cutout_bounds = extract_cutout_bounds_from_png_bytes(cutout_path_to_check.read_bytes())

    three_d_dir = get_3d_storage_dir()
    has_3d = any(
        resolve_object_glb_path(three_d_dir, uid, oid).exists() for oid in obj_ids
    )

    names = load_names()
    status = UidCacheStatusResponse(
        uid=uid,
        name=names.get(uid),
        has_background=(storage_dir / f"{uid}_background.png").exists(),
        has_cutout=bool(obj_ids),
        has_3d=has_3d,
        cutout_bounds=cutout_bounds,
    )
    logger.info(
        "Cache status: uid=%s background=%s cutout=%s 3d=%s",
        uid,
        status.has_background,
        status.has_cutout,
        status.has_3d,
    )
    return status


@router.get("/{uid}/background")
async def get_background(uid: str) -> FileResponse:
    """Serve the cached background PNG for the given UID."""
    logger.info("Background requested: uid=%s", uid)
    path = get_image_storage_dir() / f"{uid}_background.png"
    if not path.exists():
        logger.warning("Background not found: uid=%s path=%s", uid, path)
        raise HTTPException(status_code=404, detail="Background not found")
    logger.info("Background served: uid=%s path=%s", uid, path)
    return FileResponse(path, media_type="image/png")


@router.get("/{uid}/cutout")
async def get_cutout(uid: str) -> FileResponse:
    """Serve the cached cutout PNG for the given UID.

    Returns the latest (highest-id) object cutout for the session, falling back
    to the legacy ``{uid}_cutout.png`` file for sessions created before the
    numbered-object scheme was introduced.
    """
    logger.info("Cutout requested: uid=%s", uid)
    storage_dir = get_image_storage_dir()
    obj_ids = list_object_ids(storage_dir, uid)
    if not obj_ids:
        logger.warning("Cutout not found: uid=%s (no object ids)", uid)
        raise HTTPException(status_code=404, detail="Cutout not found")
    path = resolve_object_cutout_path(storage_dir, uid, max(obj_ids))
    if not path.exists():
        logger.warning("Cutout not found: uid=%s path=%s", uid, path)
        raise HTTPException(status_code=404, detail="Cutout not found")
    logger.info("Cutout served: uid=%s path=%s", uid, path)
    return FileResponse(path, media_type="image/png")


@router.get("/{uid}/original")
async def get_original_image(uid: str) -> FileResponse:
    """Serve the original uploaded image for the given UID."""
    logger.info("Original image requested: uid=%s", uid)
    storage_dir = get_image_storage_dir()
    try:
        path = get_image_path(uid, storage_dir)
    except FileNotFoundError:
        logger.warning("Original image not found: uid=%s", uid)
        raise HTTPException(status_code=404, detail="Original image not found")
    suffix = path.suffix.lower().lstrip(".")
    media_type = "image/jpeg" if suffix in ("jpg", "jpeg") else f"image/{suffix}"
    logger.info("Original image served: uid=%s path=%s", uid, path)
    return FileResponse(path, media_type=media_type)

