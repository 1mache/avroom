from __future__ import annotations

from pydantic import BaseModel, Field


class ImageProcessingOptions(BaseModel):
    """Optional knobs for image processing.

    This model exists to keep request handling explicit and typed.
    The actual processing implementation can choose to ignore some/all fields.
    """

    output_format: str = Field(
        default="png",
        description="Desired output image format (e.g. 'png', 'jpeg').",
    )
    grayscale: bool = Field(
        default=False,
        description="Whether to convert the image to grayscale.",
    )


class ClickRequest(BaseModel):
    """Request payload for a user's click on an image.

    - `image_id` is a forward-compatible placeholder for when images are persisted.
    - `x` and `y` are pixel coordinates with origin at the top-left of the image.
    """

    image_id: str = Field(
        ...,
        description="Logical identifier of the image the click refers to.",
    )
    x: int = Field(
        ...,
        ge=0,
        description="Click X coordinate in pixels from the left edge.",
    )
    y: int = Field(
        ...,
        ge=0,
        description="Click Y coordinate in pixels from the top edge.",
    )
    options: ImageProcessingOptions | None = Field(
        default=None,
        description="Optional processing options associated with the click action.",
    )


class ClickResponse(BaseModel):
    """Response payload acknowledging a click request.

    For the MVP this is just an echo/ack. Later, this can include a job id,
    derived metadata, or a URL to the processed output once storage exists.
    """

    image_id: str = Field(..., description="Echo of the image identifier.")
    x: int = Field(..., description="Echo of X coordinate (pixels).")
    y: int = Field(..., description="Echo of Y coordinate (pixels).")

