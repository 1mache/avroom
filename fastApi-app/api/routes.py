from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import Response

from core.image_processing import process_click_on_image, process_image
from schemas.image import ClickRequest, ClickResponse, ImageProcessingOptions

router = APIRouter(prefix="/images", tags=["images"])


@router.post(
    "/process",
    response_class=Response,
    responses={
        200: {
            "content": {"image/png": {}},
            "description": "Processed image bytes.",
        }
    },
)
async def upload_and_process_image(
    file: Annotated[UploadFile, File(..., description="Image file to be processed.")],
) -> Response:
    """Upload an image and receive a processed image in the response.

    The uploaded image is treated as opaque bytes. The actual transformation logic
    lives in `process_image`, which you will later replace with real processing
    code (e.g. resizing, segmentation, etc.).
    """

    file_bytes = await file.read()

    # For the outline, construct default options and pass them through.
    options = ImageProcessingOptions()
    output_bytes = process_image(input_bytes=file_bytes, options=options)

    # The processed bytes are returned directly as the HTTP response body.
    # Adjust `media_type` once you support multiple formats via `options`.
    return Response(content=output_bytes, media_type="image/png")


@router.post("/click", response_model=ClickResponse)
async def handle_click(request: ClickRequest) -> ClickResponse:
    """Handle a user's click on an image.

    The coordinates are expressed in pixels with origin at the top-left of the image.
    For now this endpoint acts as an acknowledgement and hook for future logic that
    will use `process_click_on_image` once images are persisted.
    """

    _ = process_click_on_image(
        image_id=request.image_id,
        x=request.x,
        y=request.y,
        options=request.options,
    )

    # MVP behavior: simply echo the received click information.
    return ClickResponse(image_id=request.image_id, x=request.x, y=request.y)

