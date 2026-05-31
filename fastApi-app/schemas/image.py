from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field


class SessionInfo(BaseModel):
    """Lightweight session descriptor returned by the sessions list endpoint."""

    uid: Annotated[str, Field(description="Session UID.")]
    name: Annotated[
        str | None,
        Field(default=None, description="Human-readable label set by the user, or None if unnamed."),
    ]


class SetNameRequest(BaseModel):
    """Request payload for assigning a human-readable name to a session."""

    name: Annotated[str, Field(min_length=1, description="Desired session name.")]


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


class SegmentRequest(ClickRequest):
    """Request payload for segmentation-only candidate generation."""


class CutoutBounds(BaseModel):
    """Tight visible-object bounds inside the cutout image."""

    left: Annotated[int, Field(ge=0, description="Left-most visible pixel, inclusive.")]
    top: Annotated[int, Field(ge=0, description="Top-most visible pixel, inclusive.")]
    right: Annotated[int, Field(ge=0, description="Right-most visible bound, exclusive.")]
    bottom: Annotated[int, Field(ge=0, description="Bottom-most visible bound, exclusive.")]
    natural_width: Annotated[int, Field(gt=0, description="Full cutout image width in pixels.")]
    natural_height: Annotated[int, Field(gt=0, description="Full cutout image height in pixels.")]


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


class SegmentMaskOption(BaseModel):
    """One user-selectable segmentation candidate."""

    mask_id: Annotated[
        str,
        Field(pattern=r"^\d+$", description="Identifier for the cached refined mask and cutout candidate."),
    ]
    cutout_b64: Annotated[
        str,
        Field(description="Base64-encoded BGRA cutout preview for this candidate."),
    ]
    format: Annotated[
        str,
        Field(description="Preview image format, currently 'png'."),
    ]
    cutout_bounds: Annotated[
        CutoutBounds | None,
        Field(default=None, description="Tight visible-object bounds inside this cutout PNG."),
    ]


class SegmentResponse(BaseModel):
    """Segmentation-only response with all candidate masks."""

    image_id: Annotated[
        str,
        Field(description="Identifier of the image that was segmented."),
    ]
    masks: Annotated[
        list[SegmentMaskOption],
        Field(description="User-selectable mask candidates in model return order."),
    ]


class InpaintMaskRequest(BaseModel):
    """Request payload for inpainting one selected cached mask."""

    image_id: Annotated[
        str,
        Field(description="Identifier of the image whose mask candidate should be inpainted."),
    ]
    mask_id: Annotated[
        str,
        Field(min_length=1, pattern=r"^\d+$", description="Identifier of the selected cached mask candidate."),
    ]


class InpaintMaskResponse(ClickResultResponse):
    """Final result returned after selected-mask inpainting."""

    object_id: Annotated[
        int,
        Field(
            default=0,
            ge=0,
            description="Zero-based integer id assigned to this newly created object within the session.",
        ),
    ]


class ObjectInfo(BaseModel):
    """Descriptor for one processed object within a session."""

    object_id: Annotated[
        int,
        Field(ge=0, description="Zero-based integer id for this object within the session."),
    ]
    cutout_b64: Annotated[
        str,
        Field(description="Base64-encoded BGRA cutout PNG for this object."),
    ]
    format: Annotated[
        str,
        Field(description="Image format, currently 'png'."),
    ]
    cutout_bounds: Annotated[
        CutoutBounds | None,
        Field(default=None, description="Tight visible-object bounds inside the cutout PNG."),
    ]
    has_3d: Annotated[
        bool,
        Field(description="Whether a GLB 3D model has been generated for this object."),
    ]


class ObjectListResponse(BaseModel):
    """All processed objects for a session, ordered by object id."""

    uid: Annotated[
        str,
        Field(description="Session UID."),
    ]
    objects: Annotated[
        list[ObjectInfo],
        Field(description="Objects in ascending object_id order."),
    ]


class UidCacheStatusResponse(BaseModel):
    """Indicates which processed artifacts are cached on disk for a given UID."""

    uid: Annotated[str, Field(description="Session UID.")]
    name: Annotated[
        str | None,
        Field(default=None, description="Human-readable session name, if one was set."),
    ]
    has_background: Annotated[bool, Field(description="Background PNG is cached.")]
    has_cutout: Annotated[bool, Field(description="Cutout PNG is cached.")]
    has_3d: Annotated[bool, Field(description="GLB 3D model is cached.")]
    cutout_bounds: Annotated[
        CutoutBounds | None,
        Field(default=None, description="Tight visible-object bounds for cached cutout PNG."),
    ]

