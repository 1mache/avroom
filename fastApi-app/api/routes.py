"""Upload plus finalized-object mutation routes (update/duplicate/delete/rescale).

The remaining two thirds of what used to be one 1150-line file now live in
``api/sessions.py`` (session lifecycle + pipeline submission) and
``api/object_views.py`` (read-only artifact serving) — see the module
docstrings there. This file keeps upload, warm-maps, and every route under
``/objects/{uuid}`` together because several tests import ``router`` from
this module directly (mounting only this router, bypassing ``main.py``) and
monkeypatch settings/helper functions by their `api.routes.<name>` path —
moving those call sites to another module would silently break that
patching. Same ``/images`` prefix as the other two routers; all three are
mounted together in ``main.py``.
"""

from __future__ import annotations

from typing import Annotated

import uuid
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pathlib import Path

from core.auth.admin import is_admin
from core.auth.identity import current_user_id
from core.auth.ownership import require_session_owner
from core.image_validation import ImageValidator
from core.inference_pool.client import get_inference_client
from core.inference_pool.session_runtime import (
    SessionConflictError,
    acquire_canvas_writer,
    release_canvas_writer,
)
from core.camera_calib_cache import save_camera_calib
from core.session_preview import write_upload_preview
from core.normal_cache import warm_normals_for_session
from core.object_import import ImportValidationError, import_object_cutout
from core.object_metadata import (
    ObjectMetadata,
    build_clone_metadata,
    get_object_by_uuid,
    next_object_id,
    remove_object_index_entry,
    reset_object_transform,
    save_object_metadata,
    set_object_name,
    set_object_offset,
    set_object_rescale_state,
    to_object_metadata_response,
)
from schemas.objects import (
    DuplicateObjectResponse,
    ImportObjectResponse,
    ObjectMetadataResponse,
    PlacementRequest,
    PlacementResponse,
    SmartPasteRequest,
    UpdateObjectRequest,
)
from schemas.sessions import ImageUploadResponse, WarmSessionMapsResponse
from core.object_storage import (
    copy_object_artifacts,
    delete_legacy_object_artifacts,
    delete_object_artifact_files,
    delete_object_glb_files,
    resolve_object_cutout_path,
)
from core.cutout_bounds import extract_cutout_bounds_from_png_bytes, scale_cutout_bounds
from core.repositories.session_repo import is_session_registered, register_uid, touch_session
from settings import (
    get_3d_storage_dir,
    get_image_storage_dir,
    get_upload_validation_enabled,
    get_camera_calibration_enabled,
    get_normal_map_enabled,
)

router = APIRouter(prefix="/images", tags=["images"], dependencies=[Depends(require_session_owner)])
logger = logging.getLogger(__name__)


@router.post("/upload", response_model=ImageUploadResponse)
async def upload_image(
    file: Annotated[UploadFile, File(..., description="Image file to be stored on the server.")],
    skip_validation: Annotated[
        bool, Form(description="Admin-only: bypass technical + content validation.")
    ] = False,
    user_id: str = Depends(current_user_id),
) -> ImageUploadResponse:
    """Upload an image and persist it to disk.

    The server assigns a new `image_id` and saves the file under the configured
    image storage directory. The returned `image_id` is later used by the click
    endpoint to reference this stored image.

    `skip_validation` is admin-only -- rejected with 403 for anyone else, so
    the flag can't be used to silently bypass the validation gate.
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

    if skip_validation and not is_admin(user_id):
        logger.warning("Upload rejected: non-admin requested skip_validation user_id=%s", user_id)
        raise HTTPException(status_code=403, detail="Only admins can skip upload validation.")

    if get_upload_validation_enabled() and not skip_validation:
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
        logger.info(
            "Upload validation skipped: VALIDATE=false skip_validation=%s filename=%s",
            skip_validation,
            original_filename,
        )

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

    register_uid(image_id, user_id)
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

    if get_normal_map_enabled():
        try:
            warm_normals_for_session(
                storage_dir,
                image_id,
                file_bytes,
                map_normals_from_bytes=lambda data: get_inference_client().run_map_normals(
                    image_bytes=data
                ),
            )
        except Exception as exc:
            logger.warning(
                "Upload normal-map warm failed (non-fatal): image_id=%s detail=%s",
                image_id,
                exc,
            )
    else:
        logger.info("Upload normal-map warm skipped: NORMAL_MAP=false image_id=%s", image_id)

    return ImageUploadResponse(
        image_id=image_id,
        original_filename=original_filename,
        stored_path=str(image_path),
        last_changed=last_changed,
    )


@router.post("/{uid}/warm-maps", response_model=WarmSessionMapsResponse)
def warm_session_maps_endpoint(uid: str) -> WarmSessionMapsResponse:
    """Ensure depth and normal maps exist for the session's current canvas.

    Called fire-and-forget when the workspace opens so the first segment or
    smart-paste does not pay a cold-cache model load. Does not bump
    ``last_changed``.
    """
    logger.info("Session map warm requested: uid=%s", uid)
    if not is_session_registered(uid):
        logger.warning("Session map warm failed — unknown uid: %s", uid)
        raise HTTPException(status_code=404, detail=f"Session not found for uid='{uid}'")

    storage_dir = get_image_storage_dir()
    try:
        result = get_inference_client().run_warm_session_maps(
            image_id=uid,
            base_dir=storage_dir,
        )
    except FileNotFoundError as exc:
        logger.warning("Session map warm failed — not found: uid=%s", uid)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Session map warm failed: uid=%s", uid)
        raise HTTPException(status_code=500, detail=f"Session map warm failed: {exc}") from exc

    logger.info(
        "Session map warm complete: uid=%s content_hash=%s depth_hit=%s normal_hit=%s",
        uid,
        result.content_hash[:12],
        result.depth_cache_hit,
        result.normal_cache_hit,
    )
    return WarmSessionMapsResponse(
        uid=uid,
        content_hash=result.content_hash,
        depth_cache_hit=result.depth_cache_hit,
        normal_cache_hit=result.normal_cache_hit,
    )


@router.patch("/objects/{object_uuid}", response_model=ObjectMetadataResponse)
async def update_object(object_uuid: str, request: UpdateObjectRequest) -> ObjectMetadataResponse:
    """Partially update one object identified by UUID: name, offset, and/or scale.

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

    metadata = get_object_by_uuid(object_uuid)
    if metadata is None:
        logger.warning("Object update failed — not found: uuid=%s", object_uuid)
        raise HTTPException(status_code=404, detail=f"Object not found for uuid='{object_uuid}'")

    fields = request.model_fields_set
    if "name" in fields:
        metadata = set_object_name(object_uuid, request.name)
    if "offset_x" in fields or "offset_y" in fields:
        next_offset_x = request.offset_x if request.offset_x is not None else metadata.offset_x
        next_offset_y = request.offset_y if request.offset_y is not None else metadata.offset_y
        metadata = set_object_offset(object_uuid, next_offset_x, next_offset_y)
    if "display_scale" in fields:
        assert request.display_scale is not None
        metadata = set_object_rescale_state(object_uuid, display_scale=request.display_scale)

    touch_session(metadata.session_id)
    response = to_object_metadata_response(metadata, storage_dir, get_3d_storage_dir())
    logger.info("Object updated: uuid=%s fields=%s", object_uuid, sorted(fields))
    return response


@router.post("/objects/{object_uuid}/reset-transform", response_model=ObjectMetadataResponse)
def reset_object_transform_route(object_uuid: str) -> ObjectMetadataResponse:
    """Reset drag offset and display scale to creation defaults; cutout PNG unchanged."""
    logger.info("Object transform reset requested: uuid=%s", object_uuid)
    storage_dir = get_image_storage_dir()

    metadata = get_object_by_uuid(object_uuid)
    if metadata is None:
        logger.warning("Object transform reset failed — not found: uuid=%s", object_uuid)
        raise HTTPException(status_code=404, detail=f"Object not found for uuid='{object_uuid}'")

    metadata = reset_object_transform(object_uuid)
    touch_session(metadata.session_id)
    response = to_object_metadata_response(metadata, storage_dir, get_3d_storage_dir())
    logger.info(
        "Object transform reset: uuid=%s session_id=%s object_id=%d",
        object_uuid,
        metadata.session_id,
        metadata.object_id,
    )
    return response


@router.post("/{uid}/objects/import", response_model=ImportObjectResponse, status_code=201)
async def import_object(
    uid: str,
    file: Annotated[UploadFile, File(..., description="PNG cutout to add to the session.")],
) -> ImportObjectResponse:
    """Import a user-supplied PNG cutout as a new overlay object.

    Does not modify the session background. Content/AI validation is not wired
    yet — see ``core.object_import.validate_import_cutout`` for the future seam.
    """
    logger.info(
        "Object import requested: session_id=%s filename=%s content_type=%s",
        uid,
        file.filename,
        file.content_type,
    )
    if not is_session_registered(uid):
        logger.warning("Object import failed — session not found: session_id=%s", uid)
        raise HTTPException(status_code=404, detail=f"Session not found for uid='{uid}'")

    try:
        file_bytes = await file.read()
    except Exception as exc:
        logger.error("Object import failed — could not read upload: session_id=%s", uid)
        raise HTTPException(status_code=422, detail=f"Failed to read upload: {exc}") from exc

    storage_dir = get_image_storage_dir()
    three_d_dir = get_3d_storage_dir()
    imported: ObjectMetadata | None = None
    allocated_object_id: int | None = None

    def rollback_import() -> None:
        if allocated_object_id is None:
            return
        delete_object_artifact_files(
            base_dir=storage_dir,
            glb_dir=three_d_dir,
            uid=uid,
            object_id=allocated_object_id,
        )
        if imported is not None:
            remove_object_index_entry(imported.uuid)

    try:
        try:
            acquire_canvas_writer(uid)
        except SessionConflictError as exc:
            logger.warning(
                "Object import rejected due to canvas writer timeout: session_id=%s",
                uid,
            )
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        try:
            imported = import_object_cutout(
                session_id=uid,
                base_dir=storage_dir,
                file_bytes=file_bytes,
                filename=file.filename,
                content_type=file.content_type,
            )
            allocated_object_id = imported.object_id
        finally:
            release_canvas_writer(uid)
    except ImportValidationError as exc:
        logger.warning("Object import rejected: session_id=%s reason=%s", uid, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        logger.warning("Object import failed — missing session canvas: session_id=%s", uid)
        rollback_import()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Object import failed: session_id=%s", uid)
        rollback_import()
        raise HTTPException(status_code=500, detail=f"Object import failed: {exc}") from exc

    logger.info(
        "Object import succeeded: session_id=%s object_id=%d object_uuid=%s",
        uid,
        imported.object_id,
        imported.uuid,
    )
    return ImportObjectResponse(object_uuid=imported.uuid)


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

    source = get_object_by_uuid(object_uuid)
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
            new_object_id = next_object_id(source.session_id)
            clone_metadata = build_clone_metadata(source, new_object_id, source_bounds)
            copy_object_artifacts(
                base_dir=storage_dir,
                glb_dir=three_d_dir,
                uid=source.session_id,
                source_object_id=source.object_id,
                dest_object_id=new_object_id,
            )
            save_object_metadata(clone_metadata)
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

    Removes the cutout, any GLB, all novel-view / preview caches, and the
    metadata row. Session-level artifacts —
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

    target = get_object_by_uuid(object_uuid)
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


@router.delete("/objects/{object_uuid}/3d", status_code=204)
def delete_object_3d(object_uuid: str) -> Response:
    """Remove this object's cached GLB only; cutout and metadata stay intact."""
    logger.info("Object 3D delete requested: uuid=%s", object_uuid)
    three_d_dir = get_3d_storage_dir()

    target = get_object_by_uuid(object_uuid)
    if target is None:
        logger.warning("Object 3D delete failed — not found: uuid=%s", object_uuid)
        raise HTTPException(
            status_code=404,
            detail=f"Object not found for uuid='{object_uuid}'",
        )

    removed = delete_object_glb_files(
        glb_dir=three_d_dir,
        uid=target.session_id,
        object_id=target.object_id,
    )
    if removed == 0:
        logger.warning(
            "Object 3D delete failed — no GLB on disk: uuid=%s session_id=%s object_id=%d",
            object_uuid,
            target.session_id,
            target.object_id,
        )
        raise HTTPException(status_code=404, detail="No 3D model cached for this object.")

    touch_session(target.session_id)
    logger.info(
        "Object 3D deleted: uuid=%s session_id=%s object_id=%d files_removed=%d",
        object_uuid,
        target.session_id,
        target.object_id,
        removed,
    )
    return Response(status_code=204)


@router.post("/objects/{object_uuid}/rescale-by-depth", response_model=PlacementResponse)
def rescale_object_by_depth(
    object_uuid: str,
    request: PlacementRequest,
) -> PlacementResponse:
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
    cutout_path = resolve_object_cutout_path(storage_dir, result.session_id, result.object_id)
    base_bounds = extract_cutout_bounds_from_png_bytes(cutout_path.read_bytes())
    cutout_bounds = (
        scale_cutout_bounds(base_bounds, result.display_scale) if base_bounds is not None else None
    )
    logger.info(
        "Rescale by depth complete: uuid=%s scale_factor=%.4f display_scale=%.4f target_depth=%.2f",
        object_uuid,
        result.scale_factor,
        result.display_scale,
        result.target_depth,
    )
    return PlacementResponse(
        object_uuid=result.object_uuid,
        session_id=result.session_id,
        object_id=result.object_id,
        source_average_depth=result.source_average_depth,
        target_depth=result.target_depth,
        scale_factor=result.scale_factor,
        display_scale=result.display_scale,
        cutout_bounds=cutout_bounds,
    )


@router.post("/objects/{object_uuid}/smart-paste", response_model=PlacementResponse)
def smart_paste_object(
    object_uuid: str,
    request: SmartPasteRequest,
) -> PlacementResponse:
    """Run smart paste at the given placement point."""
    logger.info(
        "Smart paste requested: uuid=%s placement=(%d,%d) scale_by_pov=%s smart_rotate=%s",
        object_uuid,
        request.x,
        request.y,
        request.scale_by_pov,
        request.smart_rotate,
    )
    storage_dir = get_image_storage_dir()
    try:
        result = get_inference_client().run_smart_paste(
            base_dir=storage_dir,
            object_uuid=object_uuid,
            x=request.x,
            y=request.y,
            scale_by_pov=request.scale_by_pov,
            smart_rotate=request.smart_rotate,
        )
    except FileNotFoundError as exc:
        logger.warning("Smart paste failed — not found: uuid=%s", object_uuid)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        logger.error("Smart paste failed — invalid input: uuid=%s reason=%s", object_uuid, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    touch_session(result.session_id)
    cutout_path = resolve_object_cutout_path(storage_dir, result.session_id, result.object_id)
    base_bounds = extract_cutout_bounds_from_png_bytes(cutout_path.read_bytes())
    cutout_bounds = (
        scale_cutout_bounds(base_bounds, result.display_scale) if base_bounds is not None else None
    )
    logger.info(
        "Smart paste complete: uuid=%s scale_factor=%.4f display_scale=%.4f target_depth=%.2f "
        "azimuth=%s rel_elevation=%s",
        object_uuid,
        result.scale_factor,
        result.display_scale,
        result.target_depth,
        result.azimuth_deg,
        result.relative_elevation_deg,
    )
    return PlacementResponse(
        object_uuid=result.object_uuid,
        session_id=result.session_id,
        object_id=result.object_id,
        source_average_depth=result.source_average_depth,
        target_depth=result.target_depth,
        scale_factor=result.scale_factor,
        display_scale=result.display_scale,
        cutout_bounds=cutout_bounds,
        azimuth_deg=result.azimuth_deg,
        relative_elevation_deg=result.relative_elevation_deg,
    )
