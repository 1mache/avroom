from __future__ import annotations

"""Legacy single-shot click/segment schemas.

Session lifecycle, object CRUD, novel-view, and batch schemas moved to
their own feature modules (schemas/sessions.py, schemas/objects.py,
schemas/novel_view.py, schemas/batch.py) -- see docs/backend/schemas.md.
What's left here is the legacy `POST /images/click` request/response plus
the segment-only variant that reuses it.
"""

from typing import Annotated

from pydantic import BaseModel, Field

from schemas.common import CutoutBounds, VerifyMode


class ImageProcessingOptions(BaseModel):
    """Optional knobs for image processing.

    This model exists to keep request handling explicit and typed.
    The actual processing implementation can choose to ignore some/all fields.
    """

    output_format: Annotated[
        str,
        Field(default="png", description="Desired output image format (e.g. 'png', 'jpeg')."),
    ]
    grayscale: Annotated[
        bool,
        Field(default=False, description="Whether to convert the image to grayscale."),
    ]


class ClickRequest(BaseModel):
    """Request payload for a user's click on an image.

    - `image_id` identifies which previously uploaded image the click refers to.
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
        Field(default=None, description="Optional processing options associated with the click action."),
    ]


class SegmentRequest(ClickRequest):
    """Request payload for segmentation-only candidate generation."""

    verify: Annotated[
        VerifyMode,
        Field(
            description=(
                "manual returns all SAM candidates for the picker; "
                "auto returns one CLIP-selected mask or 422 if none is viable."
            ),
        ),
    ] = VerifyMode.MANUAL


class ClickResultResponse(BaseModel):
    """Segmentation result returned from a click on an image.

    Both `background_b64` and `cutout_b64` contain base64-encoded image data
    that the frontend can render directly as data URLs.
    """

    image_id: Annotated[
        str,
        Field(description="Identifier of the image that was segmented."),
    ]
    background_b64: Annotated[
        str,
        Field(description="Base64-encoded background image (without the clicked object)."),
    ]
    cutout_b64: Annotated[
        str,
        Field(description="Base64-encoded cutout image containing the clicked object."),
    ]
    format: Annotated[
        str,
        Field(description="Image format used for both returned images (e.g. 'png')."),
    ]
    cutout_bounds: Annotated[
        CutoutBounds | None,
        Field(default=None, description="Tight visible-object bounds inside the cutout PNG."),
    ]
