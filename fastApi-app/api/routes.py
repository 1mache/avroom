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
    get_image_path,
    inpaint_selected_mask_on_image,
    process_click_on_image,
    segment_candidates_on_image,
)
from core.mask_cache import delete_candidates
from schemas.image import (
    ClickRequest,
    ClickResultResponse,
    CutoutBounds,
    ImageUploadResponse,
    InpaintMaskRequest,
    InpaintMaskResponse,
    SegmentMaskOption,
    SegmentRequest,
    SegmentResponse,
    SessionInfo,
    SetNameRequest,
    UidCacheStatusResponse,
)
from settings import (
    deregister_uid,
    get_3d_storage_dir,
    get_image_storage_dir,
    get_sessions_file,
    load_names,
    register_uid,
    remove_session_name,
    set_session_name,
)

router = APIRouter(prefix="/images", tags=["images"])
logger = logging.getLogger(__name__)


def _extract_cutout_bounds_from_png_bytes(image_bytes: bytes) -> CutoutBounds | None:
    """Return tight alpha bounds for a BGRA cutout PNG."""

    decoded = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if decoded is None:
        logger.warning("Failed to decode cutout bytes for bounds extraction")
        return None

    if decoded.ndim != 3 or decoded.shape[2] < 4:
        logger.warning("Cutout image missing alpha channel: shape=%s", decoded.shape)
        height, width = decoded.shape[:2]
        return CutoutBounds(
            left=0,
            top=0,
            right=width,
            bottom=height,
            natural_width=width,
            natural_height=height,
        )

    alpha = decoded[:, :, 3]
    non_zero_points = cv2.findNonZero(alpha)
    height, width = alpha.shape

    # Empty alpha should not crash cache/session restore. Fall back to full image
    # box so frontend can still treat the cutout as bounded.
    if non_zero_points is None:
        return CutoutBounds(
            left=0,
            top=0,
            right=width,
            bottom=height,
            natural_width=width,
            natural_height=height,
        )

    x, y, w, h = cv2.boundingRect(non_zero_points)
    return CutoutBounds(
        left=int(x),
        top=int(y),
        right=int(x + w),
        bottom=int(y + h),
        natural_width=int(width),
        natural_height=int(height),
    )


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
    result = [SessionInfo(uid=u, name=names.get(u)) for u in uids]
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

    return ImageUploadResponse(
        image_id=image_id,
        original_filename=original_filename,
        stored_path=str(image_path),
    )


@router.post("/click", response_model=ClickResultResponse)
async def handle_click(request: ClickRequest) -> ClickResultResponse:
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
        background_bytes, cutout_bytes, image_format = process_click_on_image(
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

    background_b64 = base64.b64encode(background_bytes).decode("ascii")
    cutout_b64 = base64.b64encode(cutout_bytes).decode("ascii")
    # Frontend uses these bounds to clamp drag by visible object, not by the
    # transparent padding that exists around most cutouts.
    cutout_bounds = _extract_cutout_bounds_from_png_bytes(cutout_bytes)

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
async def segment_image(request: SegmentRequest) -> SegmentResponse:
    """Return all mask candidates for a click without running inpainting."""

    logger.info(
        "Segmentation requested: image_id=%s x=%d y=%d",
        request.image_id,
        request.x,
        request.y,
    )

    storage_dir: Path = get_image_storage_dir()

    try:
        candidates = segment_candidates_on_image(
            image_id=request.image_id,
            base_dir=storage_dir,
            x=request.x,
            y=request.y,
            options=request.options,
        )
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
                cutout_bounds=_extract_cutout_bounds_from_png_bytes(cutout_bytes),
            )
        )

    logger.info(
        "Segmentation complete: image_id=%s candidates=%d",
        request.image_id,
        len(masks),
    )
    return SegmentResponse(image_id=request.image_id, masks=masks)


@router.post("/inpaint", response_model=InpaintMaskResponse)
async def inpaint_mask(request: InpaintMaskRequest) -> InpaintMaskResponse:
    """Inpaint background using one user-selected cached mask candidate."""

    logger.info(
        "Inpainting requested: image_id=%s mask_id=%s",
        request.image_id,
        request.mask_id,
    )

    storage_dir: Path = get_image_storage_dir()

    try:
        background_bytes, cutout_bytes, image_format = inpaint_selected_mask_on_image(
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

    background_image_path = storage_dir / f"{request.image_id}_background.png"
    background_image_path.write_bytes(background_bytes)
    cutout_image_path = storage_dir / f"{request.image_id}_cutout.png"
    cutout_image_path.write_bytes(cutout_bytes)

    # Selected candidate is now promoted to final artifacts. Remove all
    # temporary candidates so stale alternatives cannot be selected later.
    delete_candidates(storage_dir, request.image_id)

    background_b64 = base64.b64encode(background_bytes).decode("ascii")
    cutout_b64 = base64.b64encode(cutout_bytes).decode("ascii")
    cutout_bounds = _extract_cutout_bounds_from_png_bytes(cutout_bytes)

    logger.info(
        "Inpainting complete: image_id=%s mask_id=%s background_bytes=%d cutout_bytes=%d",
        request.image_id,
        request.mask_id,
        len(background_bytes),
        len(cutout_bytes),
    )

    return InpaintMaskResponse(
        image_id=request.image_id,
        background_b64=background_b64,
        cutout_b64=cutout_b64,
        format=image_format,
        cutout_bounds=cutout_bounds,
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

        for path in storage_dir.glob(f"{uid}.*"):
            path.unlink(missing_ok=True)
            removed += 1

        for suffix in ("_background.png", "_cutout.png"):
            p = storage_dir / f"{uid}{suffix}"
            if p.exists():
                p.unlink()
                removed += 1

        delete_candidates(storage_dir, uid)

        debug_path = storage_dir / "point" / f"{uid}_debug.png"
        if debug_path.exists():
            debug_path.unlink()
            removed += 1

        glb_path = get_3d_storage_dir() / f"{uid}.glb"
        if glb_path.exists():
            glb_path.unlink()
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

    logger.info("Name set: uid=%s name=%r", uid, request.name)
    return SessionInfo(uid=uid, name=request.name)


@router.get("/{uid}/cache", response_model=UidCacheStatusResponse)
async def get_uid_cache_status(uid: str) -> UidCacheStatusResponse:
    """Return which processed artifacts are cached on disk for the given UID."""
    logger.info("Cache status requested: uid=%s", uid)
    storage_dir = get_image_storage_dir()
    cutout_path = storage_dir / f"{uid}_cutout.png"
    cutout_bounds = None
    if cutout_path.exists():
        # Session restore should not need to re-run segmentation just to recover
        # drag bounds, so cache metadata derives from stored PNG on demand.
        cutout_bounds = _extract_cutout_bounds_from_png_bytes(cutout_path.read_bytes())
    names = load_names()
    status = UidCacheStatusResponse(
        uid=uid,
        name=names.get(uid),
        has_background=(storage_dir / f"{uid}_background.png").exists(),
        has_cutout=cutout_path.exists(),
        has_3d=(get_3d_storage_dir() / f"{uid}.glb").exists(),
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
    """Serve the cached cutout PNG for the given UID."""
    logger.info("Cutout requested: uid=%s", uid)
    path = get_image_storage_dir() / f"{uid}_cutout.png"
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

