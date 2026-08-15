from __future__ import annotations

from typing import Annotated

import uuid
import logging
import base64
import binascii
import io
import os

from PIL import Image, UnidentifiedImageError

from fastapi import APIRouter, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pathlib import Path

from core.image_processing import (
    build_object_metadata_for_inpaint,
    debug_click_image_path,
    get_image_path,
)
from core.image_codec import to_base64_ascii
from core.image_validation import ImageValidationError, ImageValidator
from core.inference_pool.client import InferenceJobError, get_inference_client
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
from core.camera_calib_cache import delete_session_camera_calib, save_camera_calib
from core.session_preview import write_upload_preview
from core.object_metadata import (
    ObjectMetadata,
    build_clone_metadata,
    get_object_by_uuid,
    load_object_metadata,
    remove_object_index_entry,
    save_object_metadata,
    set_object_name,
    set_object_offset,
    delete_session_metadata,
)
from schemas.image import (
    ClickRequest,
    ClickResultResponse,
    DuplicateObjectResponse,
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
    SessionPreviewRequest,
    SessionSyncCheckRequest,
    SessionSyncCheckResponse,
    SetNameRequest,
    UpdateObjectRequest,
    RescaleByDepthRequest,
    RescaleByDepthResponse,
    UidCacheStatusResponse,
)
from core.object_storage import (
    copy_object_artifacts,
    current_background_path,
    delete_legacy_object_artifacts,
    delete_object_artifact_files,
    legacy_object_cutout_path,
    legacy_object_glb_path,
    list_object_ids,
    next_object_id,
    object_cutout_path,
    object_glb_path,
    remove_file,
    resolve_object_cutout_path,
    resolve_object_glb_path,
    session_preview_path,
)
from core.cutout_bounds import extract_cutout_bounds_from_png_bytes
from settings import (
    clear_session_last_changed,
    deregister_uid,
    get_3d_storage_dir,
    get_image_storage_dir,
    get_session_last_changed,
    evaluate_session_sync,
    is_session_registered,
    load_names,
    load_session_uids,
    register_uid,
    remove_session_name,
    get_upload_validation_enabled,
    get_camera_calibration_enabled,
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
    uids = load_session_uids()
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

    if get_upload_validation_enabled():
        # ImageValidationError is itself a ValueError; both mean "rejected".
        try:
            ImageValidator().validate(
                file_bytes,
                filename=original_filename,
                content_type=file.content_type,
            )
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
    else:
        logger.info("Upload validation skipped: VALIDATE=false filename=%s", original_filename)

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

    write_upload_preview(storage_dir, image_id, file_bytes)

    if get_camera_calibration_enabled():
        try:
            calib_outcome = get_inference_client().run_calibrate_camera(image_bytes=file_bytes)
            save_camera_calib(storage_dir, image_id, calib_outcome.to_cache_dict())
        except Exception as exc:
            logger.warning(
                "Upload camera calibration failed (non-fatal): image_id=%s detail=%s",
                image_id,
                exc,
            )
    else:
        logger.info("Upload camera calibration skipped: CAMERA_CALIB=false image_id=%s", image_id)

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


@router.post("/segment", response_model=SegmentResponse)
def segment_image(request: SegmentRequest) -> SegmentResponse:
    """Return all mask candidates for a click without running inpainting."""

    logger.info(
        "Segmentation requested: image_id=%s x=%d y=%d verify=%s",
        request.image_id,
        request.x,
        request.y,
        request.verify.value,
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
            verify=request.verify.value,
        )
    except SessionConflictError as exc:
        logger.warning("Segmentation rejected due to session conflict: %s", exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        logger.exception("Segmentation failed due to invalid input")
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except InferenceJobError as exc:
        if str(exc) == "no viable mask":
            logger.warning(
                "Auto mask pick found no viable candidate: image_id=%s",
                request.image_id,
            )
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        logger.exception("Segmentation failed")
        raise HTTPException(status_code=500, detail=f"Segmentation failed: {exc}") from exc
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
                cutout_b64=to_base64_ascii(cutout_bytes),
                format="png",
                cutout_bounds=extract_cutout_bounds_from_png_bytes(cutout_bytes),
            )
        )

    logger.info(
        "Segmentation complete: image_id=%s candidates=%d verify=%s",
        request.image_id,
        len(masks),
        request.verify.value,
    )
    return SegmentResponse(image_id=request.image_id, masks=masks)


@router.post("/inpaint", response_model=InpaintMaskResponse)
def inpaint_mask(request: InpaintMaskRequest) -> InpaintMaskResponse:
    """Inpaint background using one user-selected cached mask candidate."""

    logger.info(
        "Inpainting requested: image_id=%s mask_id=%s verify=%s",
        request.image_id,
        request.mask_id,
        request.verify.value,
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

    background_b64 = to_base64_ascii(background_bytes)
    cutout_b64 = to_base64_ascii(cutout_bytes)
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
        source_elevation_deg=object_metadata.source_elevation_deg,
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

        # Collect per-object ids before deleting files (list_object_ids scans disk).
        obj_ids = list_object_ids(storage_dir, uid)

        # Remove all numbered per-object cutouts and GLB files.
        for oid in obj_ids:
            removed += remove_file(object_cutout_path(storage_dir, uid, oid))
            removed += remove_file(object_glb_path(three_d_dir, uid, oid))

        delete_session_metadata(storage_dir, uid, obj_ids)
        removed += delete_session_depth_maps(storage_dir, uid)
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
async def sync_check_session(uid: str, request: SessionSyncCheckRequest) -> SessionSyncCheckResponse:
    """Compare a client-held session timestamp against server truth."""
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
        source_elevation_deg=metadata.source_elevation_deg,
        content_hash=metadata.content_hash,
        created_at=metadata.created_at,
        has_3d=has_3d,
        cutout_bounds=cutout_bounds,
        offset_x=metadata.offset_x,
        offset_y=metadata.offset_y,
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
async def update_object(object_uuid: str, request: UpdateObjectRequest) -> ObjectMetadataResponse:
    """Partially update one object identified by UUID: name and/or drag offset.

    Only fields actually present in the request body are touched --
    ``request.model_fields_set`` distinguishes an omitted field from an
    explicit ``null``, so a drag-persist call (offset only) can never
    accidentally clear the name, and a rename call (name only) can never
    accidentally reset the offset back to (0, 0).
    """
    logger.info(
        "Object update requested: uuid=%s fields=%s",
        object_uuid,
        sorted(request.model_fields_set),
    )
    storage_dir = get_image_storage_dir()

    metadata = get_object_by_uuid(storage_dir, object_uuid)
    if metadata is None:
        logger.warning("Object update failed — not found: uuid=%s", object_uuid)
        raise HTTPException(status_code=404, detail=f"Object not found for uuid='{object_uuid}'")

    fields = request.model_fields_set
    if "name" in fields:
        metadata = set_object_name(storage_dir, object_uuid, request.name)
    if "offset_x" in fields or "offset_y" in fields:
        next_offset_x = request.offset_x if request.offset_x is not None else metadata.offset_x
        next_offset_y = request.offset_y if request.offset_y is not None else metadata.offset_y
        metadata = set_object_offset(storage_dir, object_uuid, next_offset_x, next_offset_y)

    touch_session(metadata.session_id)
    response = _metadata_to_response(metadata, storage_dir, get_3d_storage_dir())
    logger.info("Object updated: uuid=%s fields=%s", object_uuid, sorted(fields))
    return response


@router.post("/objects/{object_uuid}/duplicate", response_model=DuplicateObjectResponse)
def duplicate_object(object_uuid: str) -> DuplicateObjectResponse:
    """Clone one object into a new object within the same session.

    Copies the cutout and any available GLB / novel-view caches. Session-level
    artifacts (background, depth cache, original upload) are shared, not
    duplicated. The clone receives a fresh UUID, sequential object_id, and a
    ``<root>-copy`` / ``<root>-copyN`` nickname.
    """
    logger.info("Object duplicate requested: uuid=%s", object_uuid)
    storage_dir = get_image_storage_dir()
    three_d_dir = get_3d_storage_dir()

    source = get_object_by_uuid(storage_dir, object_uuid)
    if source is None:
        logger.warning("Object duplicate failed — not found: uuid=%s", object_uuid)
        raise HTTPException(
            status_code=404,
            detail=f"Object not found for uuid='{object_uuid}'",
        )

    source_cutout = resolve_object_cutout_path(
        storage_dir, source.session_id, source.object_id
    )
    if not source_cutout.exists():
        logger.warning(
            "Object duplicate failed — cutout missing: uuid=%s session_id=%s object_id=%d",
            object_uuid,
            source.session_id,
            source.object_id,
        )
        raise HTTPException(
            status_code=404,
            detail=(
                f"Source cutout not found for uuid='{object_uuid}' "
                f"(session_id='{source.session_id}', object_id={source.object_id})"
            ),
        )

    # Drives a small leftward nudge on the clone's position (build_clone_metadata)
    # so it doesn't land exactly on top of its source. None (undecodable cutout)
    # falls back to copying the source's offset unchanged -- never worth failing
    # the duplicate over.
    source_bounds = extract_cutout_bounds_from_png_bytes(source_cutout.read_bytes())

    new_object_id: int | None = None
    clone_metadata: ObjectMetadata | None = None

    def rollback_clone() -> None:
        """Undo a partially written clone so no orphan cutout survives the failure."""
        if new_object_id is None:
            return
        delete_object_artifact_files(
            base_dir=storage_dir,
            glb_dir=three_d_dir,
            uid=source.session_id,
            object_id=new_object_id,
        )
        if clone_metadata is not None:
            remove_object_index_entry(clone_metadata.uuid)

    try:
        try:
            acquire_canvas_writer(source.session_id)
        except SessionConflictError as exc:
            logger.warning(
                "Object duplicate rejected due to canvas writer timeout: uuid=%s",
                object_uuid,
            )
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        try:
            new_object_id = next_object_id(storage_dir, source.session_id)
            clone_metadata = build_clone_metadata(storage_dir, source, new_object_id, source_bounds)
            copy_object_artifacts(
                base_dir=storage_dir,
                glb_dir=three_d_dir,
                uid=source.session_id,
                source_object_id=source.object_id,
                dest_object_id=new_object_id,
            )
            save_object_metadata(storage_dir, clone_metadata)
            touch_session(source.session_id)
        finally:
            release_canvas_writer(source.session_id)
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        logger.warning("Object duplicate failed — missing artifact: uuid=%s detail=%s", object_uuid, exc)
        rollback_clone()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Object duplicate failed: uuid=%s", object_uuid)
        rollback_clone()
        raise HTTPException(status_code=500, detail=f"Object duplicate failed: {exc}") from exc

    assert clone_metadata is not None
    logger.info(
        "Object duplicated: source_uuid=%s clone_uuid=%s session_id=%s "
        "source_id=%d clone_id=%d name=%r",
        object_uuid,
        clone_metadata.uuid,
        clone_metadata.session_id,
        source.object_id,
        clone_metadata.object_id,
        clone_metadata.name,
    )
    return DuplicateObjectResponse(object_uuid=clone_metadata.uuid)


@router.delete("/objects/{object_uuid}", status_code=204)
def delete_object(object_uuid: str) -> Response:
    """Permanently delete one object and all its per-object artifacts.

    Removes the cutout, any GLB, all novel-view / preview caches, the
    metadata JSON, and the UUID index entry. Session-level artifacts —
    background canvas, depth cache, camera calibration, the original upload,
    and the dashboard preview thumbnail — are shared with surviving objects
    and are never touched here. In particular the background canvas already
    has this object's region inpainted out; deleting the object does not
    restore those pixels, it only removes the object's own cutout layer.

    Plain ``def``, not ``async def``: this blocks on the canvas writer lock,
    same as ``duplicate_object`` (see ``tests/test_concurrency.py``).
    """
    logger.info("Object delete requested: uuid=%s", object_uuid)
    storage_dir = get_image_storage_dir()
    three_d_dir = get_3d_storage_dir()

    target = get_object_by_uuid(storage_dir, object_uuid)
    if target is None:
        logger.warning("Object delete failed — not found: uuid=%s", object_uuid)
        raise HTTPException(
            status_code=404,
            detail=f"Object not found for uuid='{object_uuid}'",
        )

    try:
        try:
            acquire_canvas_writer(target.session_id)
        except SessionConflictError as exc:
            logger.warning(
                "Object delete rejected due to canvas writer timeout: uuid=%s",
                object_uuid,
            )
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        try:
            removed = delete_object_artifact_files(
                base_dir=storage_dir,
                glb_dir=three_d_dir,
                uid=target.session_id,
                object_id=target.object_id,
                include_metadata=True,
            )
            if target.object_id == 0:
                removed += delete_legacy_object_artifacts(
                    base_dir=storage_dir,
                    glb_dir=three_d_dir,
                    uid=target.session_id,
                )
            remove_object_index_entry(object_uuid)
            touch_session(target.session_id)
        finally:
            release_canvas_writer(target.session_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Object delete failed: uuid=%s", object_uuid)
        raise HTTPException(status_code=500, detail=f"Object delete failed: {exc}") from exc

    logger.info(
        "Object deleted: uuid=%s session_id=%s object_id=%d files_removed=%d",
        object_uuid,
        target.session_id,
        target.object_id,
        removed,
    )
    return Response(status_code=204)


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
        cutout_b64=to_base64_ascii(result.cutout_bytes),
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
            cutout_b64 = to_base64_ascii(cutout_bytes)
            cutout_bounds = extract_cutout_bounds_from_png_bytes(cutout_bytes)
            has_3d = resolve_object_glb_path(three_d_dir, uid, oid).exists()
            # Metadata is absent for objects created before it was introduced;
            # those fall back to nulls plus an unmoved (0, 0) offset.
            meta = load_object_metadata(storage_dir, uid, oid)
            objects_list.append(
                ObjectInfo(
                    object_id=oid,
                    uuid=meta.uuid if meta is not None else None,
                    name=meta.name if meta is not None else None,
                    average_depth=meta.average_depth if meta is not None else None,
                    source_elevation_deg=(
                        meta.source_elevation_deg if meta is not None else None
                    ),
                    cutout_b64=cutout_b64,
                    format="png",
                    cutout_bounds=cutout_bounds,
                    has_3d=has_3d,
                    offset_x=meta.offset_x if meta is not None else 0.0,
                    offset_y=meta.offset_y if meta is not None else 0.0,
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
        has_background=current_background_path(storage_dir, uid).exists(),
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
    path = current_background_path(get_image_storage_dir(), uid)
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


@router.get("/{uid}/preview")
async def get_session_preview(uid: str) -> FileResponse:
    """Serve the dashboard thumbnail for the given UID.

    Written at upload time (a downscaled copy of the original) and
    overwritten by the frontend after each edit settles, so it always shows
    the room roughly as the user left it. Returns 404 when absent — callers
    (the dashboard card) fall back to a placeholder rather than treating this
    as an error.
    """
    logger.info("Session preview requested: uid=%s", uid)
    path = session_preview_path(get_image_storage_dir(), uid)
    if not path.exists():
        logger.warning("Session preview not found: uid=%s path=%s", uid, path)
        raise HTTPException(status_code=404, detail="Preview not found")
    logger.info("Session preview served: uid=%s path=%s", uid, path)
    return FileResponse(path, media_type="image/jpeg")


@router.post("/{uid}/preview", status_code=204)
async def save_session_preview(uid: str, request: SessionPreviewRequest) -> Response:
    """Store a client-composited dashboard thumbnail for the given UID.

    Called fire-and-forget from the frontend, debounced, after edits settle
    (see ``composeSessionPreview`` / ``saveSessionPreview`` in the React app).
    Does not call ``touch_session``: the mutation that triggered this preview
    already bumped ``last_changed`` well before the debounced capture runs,
    so the dashboard's cache-buster is already correct, and bumping it again
    here would spin an extra, pointless sync-check reconcile in the open
    workspace.
    """
    logger.info("Session preview save requested: uid=%s", uid)
    if not is_session_registered(uid):
        logger.warning("Session preview save failed — unknown uid: %s", uid)
        raise HTTPException(status_code=404, detail=f"Session not found for uid='{uid}'")

    try:
        image_bytes = base64.b64decode(request.image_b64, validate=True)
    except (ValueError, binascii.Error) as exc:
        logger.warning("Session preview save rejected — invalid base64: uid=%s detail=%s", uid, exc)
        raise HTTPException(status_code=422, detail="image_b64 is not valid base64.") from exc

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img.verify()
    except (UnidentifiedImageError, OSError) as exc:
        logger.warning("Session preview save rejected — not a valid image: uid=%s detail=%s", uid, exc)
        raise HTTPException(status_code=422, detail="image_b64 does not decode to a valid image.") from exc

    storage_dir = get_image_storage_dir()
    storage_dir.mkdir(parents=True, exist_ok=True)
    path = session_preview_path(storage_dir, uid)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    try:
        tmp_path.write_bytes(image_bytes)
        os.replace(tmp_path, path)
    except OSError as exc:
        logger.error("Session preview save failed: uid=%s error=%s", uid, exc)
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Preview save failed: {exc}") from exc

    logger.info("Session preview saved: uid=%s path=%s size_bytes=%d", uid, path, len(image_bytes))
    return Response(status_code=204)

