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


class ImageUploadResponse(BaseModel):
    """Response returned after successfully uploading and storing an image.

    The `image_id` is what the frontend will use to reference this uploaded image.
    """

    image_id: Annotated[
        str,
        Field(description="Server-generated identifier for the stored image."),
    ]
    original_filename: Annotated[
        str | None,
        Field(
            default=None,
            description="Original filename sent by the client, if available.",
        ),
    ]
    stored_path: Annotated[
        str | None,
        Field(
            default=None,
            description="Absolute or relative filesystem path where the image is stored (for debugging).",
        ),
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
        Field(description="Optional processing options associated with the click action."),
    ] = None

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


class UidCacheStatusResponse(BaseModel):
    """Indicates which processed artifacts are cached on disk for a given UID."""

    uid: Annotated[str, Field(description="Session UID.")]
    has_background: Annotated[bool, Field(description="Background PNG is cached.")]
    has_cutout: Annotated[bool, Field(description="Cutout PNG is cached.")]
    has_3d: Annotated[bool, Field(description="GLB 3D model is cached.")]

