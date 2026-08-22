from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from avroom_object_removal.ai_engines.novel_view import (
    AzimuthDirection,
    ElevationDirection,
    ZoomDirection,
)

from schemas.common import CutoutBounds  # re-exported: many modules import CutoutBounds from here
from schemas.jobs import JobInfo

# Fallback source elevation used whenever an object predates elevation
# estimation or its metadata could not be read. Kept here so the schemas, the
# stored metadata model and the novel-view endpoint cannot drift apart.
DEFAULT_SOURCE_ELEVATION_DEG = 15.0


class SessionInfo(BaseModel):
    """Lightweight session descriptor returned by the sessions list endpoint."""

    uid: Annotated[str, Field(description="Session UID.")]
    name: Annotated[
        str | None,
        Field(default=None, description="Human-readable label set by the user, or None if unnamed."),
    ]
    last_changed: Annotated[
        str | None,
        Field(
            default=None,
            description="ISO-8601 UTC timestamp of the last client-visible session mutation, if any.",
        ),
    ]


class SessionSyncCheckRequest(BaseModel):
    """Request payload for checking whether a client session snapshot is still current."""

    client_last_changed: Annotated[
        str | None,
        Field(
            default=None,
            description="ISO-8601 UTC timestamp the client believes is current; null when unknown.",
        ),
    ]


class SessionSyncCheckResponse(BaseModel):
    """Result of comparing a client session timestamp against server truth."""

    last_changed: Annotated[
        str,
        Field(
            description=(
                "Server-side last-changed ISO-8601 UTC timestamp. Empty string when "
                "the session exists but has not been touched since this feature was added."
            ),
        ),
    ]
    needs_refresh: Annotated[
        bool,
        Field(description="True when the client must re-poll session data from the server."),
    ]
    jobs: Annotated[
        list[JobInfo],
        Field(
            default_factory=list,
            description="This session's non-done jobs plus unconsumed segment results, oldest first.",
        ),
    ]


class SessionPreviewRequest(BaseModel):
    """Request payload for POST /images/{uid}/preview.

    The frontend composites the inpainted background with every visible
    cutout at its current position onto an offscreen canvas and posts the
    result here, best-effort and debounced, so the dashboard can show each
    session as the user left it.
    """

    image_b64: Annotated[
        str,
        Field(min_length=1, description="Base64-encoded preview JPEG (no data: prefix)."),
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
        Field(default="png", description="Desired output image format (e.g. 'png', 'jpeg')."),
    ]
    grayscale: Annotated[
        bool,
        Field(default=False, description="Whether to convert the image to grayscale."),
    ]


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
    last_changed: Annotated[
        str,
        Field(description="ISO-8601 UTC timestamp recorded when this session was created."),
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


class UpdateObjectRequest(BaseModel):
    """Partial update for one object by UUID: name and/or drag offset.

    Each field is independently optional so a caller can send just a rename
    or just a position update. ``name``'s ``None`` means "clear the name"
    (existing behavior). ``offset_x``/``offset_y``'s ``None`` means "not
    included in this request" -- the handler distinguishes an omitted field
    from an explicit ``null`` via ``model_fields_set``, so a drag-persist
    call (which never mentions ``name``) can never accidentally clear it,
    and vice versa.
    """

    name: Annotated[
        str | None,
        Field(default=None, description="New object name, or null to clear. Omit to leave unchanged."),
    ]
    offset_x: Annotated[
        float | None,
        Field(default=None, description="New drag offset X, natural-image pixels. Omit to leave unchanged."),
    ]
    offset_y: Annotated[
        float | None,
        Field(default=None, description="New drag offset Y, natural-image pixels. Omit to leave unchanged."),
    ]


class DuplicateObjectResponse(BaseModel):
    """Result of cloning one object into a new object within the same session."""

    object_uuid: Annotated[
        str,
        Field(description="Server-generated UUID of the newly cloned object."),
    ]


class RescaleByDepthRequest(BaseModel):
    """Request payload for depth-proportional cutout rescaling at a placement point."""

    x: Annotated[
        int,
        Field(ge=0, description="Placement X coordinate in natural-image pixels."),
    ]
    y: Annotated[
        int,
        Field(ge=0, description="Placement Y coordinate in natural-image pixels."),
    ]


class RescaleByDepthResponse(BaseModel):
    """Result of rescaling one object cutout based on depth at a placement point."""

    object_uuid: Annotated[str, Field(description="Server-generated UUID for this object.")]
    session_id: Annotated[str, Field(description="Session UID.")]
    object_id: Annotated[int, Field(ge=0, description="Zero-based integer id within the session.")]
    source_average_depth: Annotated[
        float,
        Field(description="Object average depth before this rescale."),
    ]
    target_depth: Annotated[
        float,
        Field(description="Sampled uint8 depth at the placement point."),
    ]
    scale_factor: Annotated[
        float,
        Field(description="Applied scale factor (target_depth / source_average_depth)."),
    ]
    cutout_b64: Annotated[
        str,
        Field(description="Base64-encoded rescaled BGRA cutout PNG."),
    ]
    format: Annotated[
        str,
        Field(description="Image format, currently 'png'."),
    ]
    cutout_bounds: Annotated[
        CutoutBounds | None,
        Field(default=None, description="Tight visible-object bounds inside the rescaled cutout PNG."),
    ]


class ObjectMetadataResponse(BaseModel):
    """Metadata record for one finalized object."""

    uuid: Annotated[str, Field(description="Server-generated UUID; primary searchable key.")]
    session_id: Annotated[str, Field(description="Session UID.")]
    object_id: Annotated[int, Field(ge=0, description="Zero-based integer id within the session.")]
    name: Annotated[str | None, Field(default=None, description="Optional human-readable label.")]
    average_depth: Annotated[
        float,
        Field(description="Mean uint8 depth over the selected mask at creation."),
    ]
    source_elevation_deg: Annotated[
        float,
        Field(
            default=DEFAULT_SOURCE_ELEVATION_DEG,
            description="Estimated Zero123 source elevation for this object (degrees).",
        ),
    ]
    content_hash: Annotated[
        str,
        Field(description="SHA-256 hex of canvas bytes when the object was created."),
    ]
    created_at: Annotated[str, Field(description="ISO-8601 UTC timestamp of object creation.")]
    has_3d: Annotated[
        bool,
        Field(default=False, description="Whether a GLB 3D model has been generated for this object."),
    ]
    cutout_bounds: Annotated[
        CutoutBounds | None,
        Field(default=None, description="Tight visible-object bounds inside the cutout PNG."),
    ]
    offset_x: Annotated[
        float,
        Field(default=0.0, description="Persisted drag offset X, natural-image pixels."),
    ]
    offset_y: Annotated[
        float,
        Field(default=0.0, description="Persisted drag offset Y, natural-image pixels."),
    ]


class ObjectInfo(BaseModel):
    """Descriptor for one processed object within a session."""

    object_id: Annotated[
        int,
        Field(ge=0, description="Zero-based integer id for this object within the session."),
    ]
    uuid: Annotated[
        str | None,
        Field(default=None, description="Server-generated UUID, if metadata was persisted."),
    ]
    name: Annotated[
        str | None,
        Field(default=None, description="Optional human-readable label."),
    ]
    average_depth: Annotated[
        float | None,
        Field(default=None, description="Mean uint8 depth over mask at creation."),
    ]
    source_elevation_deg: Annotated[
        float | None,
        Field(default=None, description="Estimated Zero123 source elevation (degrees)."),
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
    offset_x: Annotated[
        float,
        Field(default=0.0, description="Persisted drag offset X, natural-image pixels."),
    ]
    offset_y: Annotated[
        float,
        Field(default=0.0, description="Persisted drag offset Y, natural-image pixels."),
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


class NovelViewRequest(BaseModel):
    """Request payload for POST /images/novel-view."""

    uid: Annotated[
        str,
        Field(min_length=1, description="Session UID used to locate the cutout PNG."),
    ]
    object_id: Annotated[
        int,
        Field(ge=0, description="Zero-based object id within the session."),
    ]
    elevation_deg: Annotated[
        float,
        Field(description="Absolute elevation of the source view in degrees."),
    ]
    azimuth_deg: Annotated[
        float,
        Field(
            description=(
                "Relative azimuth to the target view in degrees. Signed when no "
                "azimuth_direction is set; otherwise an unsigned magnitude."
            ),
        ),
    ]
    azimuth_direction: Annotated[
        AzimuthDirection | None,
        Field(
            default=None,
            description=(
                "Optional horizontal orbit hint. CLOCKWISE -> positive azimuth, "
                "C_CLOCKWISE -> negative (viewed from above)."
            ),
        ),
    ]
    relative_elevation_deg: Annotated[
        float,
        Field(
            default=0.0,
            description=(
                "Relative elevation delta to the target view. Signed when no "
                "elevation_direction is set; otherwise an unsigned magnitude."
            ),
        ),
    ]
    elevation_direction: Annotated[
        ElevationDirection | None,
        Field(
            default=None,
            description="Optional tilt hint. UP -> positive delta, DOWN -> negative.",
        ),
    ]
    radius: Annotated[
        float,
        Field(
            default=0.0,
            description=(
                "Optional zoom / camera distance delta. Signed when no zoom_direction "
                "is set; otherwise an unsigned magnitude (0 = model default)."
            ),
        ),
    ]
    zoom_direction: Annotated[
        ZoomDirection | None,
        Field(
            default=None,
            description=(
                "Optional zoom hint. ZOOM_IN -> closer (negative radius), "
                "ZOOM_OUT -> farther (positive radius)."
            ),
        ),
    ]


class NovelViewResponse(BaseModel):
    """Novel-view synthesis result for a segmented object cutout."""

    uid: Annotated[str, Field(description="Echo of request session UID.")]
    object_id: Annotated[int, Field(ge=0, description="Echo of request object id.")]
    image_b64: Annotated[str, Field(description="Base64-encoded novel-view PNG (RGBA preferred).")]
    format: Annotated[str, Field(description="Image encoding, e.g. 'png'.")]
    cutout_bounds: Annotated[
        CutoutBounds | None,
        Field(default=None, description="Alpha bbox of the returned PNG when computable."),
    ]
    elevation_deg: Annotated[float, Field(description="Echo of source elevation used.")]
    azimuth_deg: Annotated[
        float,
        Field(description="Resolved signed target azimuth passed to the model."),
    ]
    azimuth_direction: Annotated[
        AzimuthDirection | None,
        Field(default=None, description="Echo of azimuth_direction when supplied."),
    ]
    relative_elevation_deg: Annotated[
        float,
        Field(description="Resolved signed relative elevation passed to the model."),
    ]
    elevation_direction: Annotated[
        ElevationDirection | None,
        Field(default=None, description="Echo of elevation_direction when supplied."),
    ]
    radius: Annotated[float, Field(description="Resolved signed radius passed to the model.")]
    zoom_direction: Annotated[
        ZoomDirection | None,
        Field(default=None, description="Echo of zoom_direction when supplied."),
    ]


class NovelViewPreviewCacheRequest(BaseModel):
    """Request payload for POST /images/novel-view/preview-cache.

    Lets the frontend persist a client-rendered stand-in (a WebGL viewport
    snapshot, already composited onto a full-canvas frame) as a best-effort
    fallback while the real synthesis request is still in flight. Written to a
    separate ``*.preview.png`` path so it can never be mistaken for a genuine
    cached result by ``POST /images/novel-view``'s own cache check.
    """

    uid: Annotated[str, Field(min_length=1, description="Session UID.")]
    object_id: Annotated[int, Field(ge=0, description="Zero-based object id within the session.")]
    azimuth_deg: Annotated[
        float,
        Field(description="Signed azimuth this preview approximates (pre-snap, matches the pending real request)."),
    ]
    relative_elevation_deg: Annotated[
        float,
        Field(default=0.0, description="Signed relative elevation this preview approximates."),
    ]
    image_b64: Annotated[str, Field(description="Base64-encoded preview PNG.")]

