from __future__ import annotations

from typing import Annotated

import uuid
import logging
import base64

import json

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pathlib import Path

from core.image_processing import get_image_path, process_click_on_image
from schemas.image import (
    ClickRequest,
    ClickResultResponse,
    ImageUploadResponse,
    UidCacheStatusResponse,
)
from settings import get_3d_storage_dir, get_image_storage_dir, get_sessions_file, register_uid

router = APIRouter(prefix="/images", tags=["images"])
logger = logging.getLogger(__name__)


@router.get("/sessions")
async def get_sessions() -> list[str]:
    """Return all image UIDs registered via upload."""
    sessions_file = get_sessions_file()
    if not sessions_file.exists():
        return []
    try:
        return json.loads(sessions_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        return []


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
    )


@router.get("/{uid}/cache", response_model=UidCacheStatusResponse)
async def get_uid_cache_status(uid: str) -> UidCacheStatusResponse:
    """Return which processed artifacts are cached on disk for the given UID."""
    logger.info("Cache status requested: uid=%s", uid)
    storage_dir = get_image_storage_dir()
    status = UidCacheStatusResponse(
        uid=uid,
        has_background=(storage_dir / f"{uid}_background.png").exists(),
        has_cutout=(storage_dir / f"{uid}_cutout.png").exists(),
        has_3d=(get_3d_storage_dir() / f"{uid}.glb").exists(),
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

