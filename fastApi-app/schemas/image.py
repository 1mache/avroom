from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field


class ImageProcessingOptions(BaseModel):
    """Optional knobs for image processing.

    This model exists to keep request handling explicit and typed.
    The actual processing implementation can choose to ignore some/all fields.
    """

    output_format: Annotated[
        str,
        Field(description="Desired output image format (e.g. 'png', 'jpeg')."),
    ] = "png"
    grayscale: Annotated[
        bool,
        Field(description="Whether to convert the image to grayscale."),
    ] = False


class ClickRequest(BaseModel):
    """Request payload for a user's click on an image.

    - `image_id` is a forward-compatible placeholder for when images are persisted.
    - `x` and `y` are pixel coordinates with origin at the top-left of the image.
    """

    image_id: Annotated[
        str,
        Field(description="Logical identifier of the image the click refers to."),
    ]
    x: Annotated[
        int,
        Field(ge=0, description="Click X coordinate in pixels from the left edge."),
    ]
    y: Annotated[
        int,
        Field(ge=0, description="Click Y coordinate in pixels from the top edge."),
    ]
    options: Annotated[
        ImageProcessingOptions | None,
        Field(description="Optional processing options associated with the click action."),
    ] = None


class ClickResponse(BaseModel):
    """Response payload acknowledging a click request.

    For the MVP this is just an echo/ack. Later, this can include a job id,
    derived metadata, or a URL to the processed output once storage exists.
    """

    image_id: Annotated[str, Field(description="Echo of the image identifier.")]
    x: Annotated[int, Field(description="Echo of X coordinate (pixels).")]
    y: Annotated[int, Field(description="Echo of Y coordinate (pixels).")]

