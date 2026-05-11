from __future__ import annotations

from typing import Annotated

import uuid
import logging
import base64

from fastapi import APIRouter, File, HTTPException, UploadFile
from pathlib import Path

from core.image_processing import process_click_on_image
from schemas.image import (
    ClickRequest,
    ClickResultResponse,
    ImageUploadResponse,
)
from settings import get_image_storage_dir

router = APIRouter(prefix="/images", tags=["images"])
logger = logging.getLogger(__name__)


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

