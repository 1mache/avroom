from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from schemas.common import CutoutBounds, DEFAULT_SOURCE_ELEVATION_DEG


class ObjectFields(BaseModel):
    """Fields shared by every model describing one object's current state.

    Base for :class:`ObjectMetadataResponse`, :class:`ObjectInfo`, and
    ``core/object_metadata.py``'s persisted ``ObjectMetadata`` -- the three
    places this shape used to be hand-copied. ``cutout_bounds`` is
    deliberately not here: it's derived at read time from the cutout PNG on
    the two API responses, but never stored on ``ObjectMetadata`` itself.
    """

    name: Annotated[str | None, Field(default=None, description="Optional human-readable label.")]
    offset_x: Annotated[
        float,
        Field(default=0.0, description="Persisted drag offset X, natural-image pixels."),
    ]
    offset_y: Annotated[
        float,
        Field(default=0.0, description="Persisted drag offset Y, natural-image pixels."),
    ]
    display_scale: Annotated[
        float,
        Field(
            default=1.0,
            gt=0.0,
            description="UI display scale vs original cutout size; cutout PNG stays at original resolution.",
        ),
    ]


class ObjectMetadataResponse(ObjectFields):
    """Metadata record for one finalized object."""

    uuid: Annotated[str, Field(description="Server-generated UUID; primary searchable key.")]
    session_id: Annotated[str, Field(description="Session UID.")]
    object_id: Annotated[int, Field(ge=0, description="Zero-based integer id within the session.")]
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


class ObjectInfo(ObjectFields):
    """Descriptor for one processed object within a session."""

    object_id: Annotated[
        int,
        Field(ge=0, description="Zero-based integer id for this object within the session."),
    ]
    uuid: Annotated[
        str | None,
        Field(default=None, description="Server-generated UUID, if metadata was persisted."),
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


class PlacementRequest(BaseModel):
    """Request payload for a placement-point operation (rescale-by-depth, smart-paste)."""

    x: Annotated[
        int,
        Field(ge=0, description="Placement X coordinate in natural-image pixels."),
    ]
    y: Annotated[
        int,
        Field(ge=0, description="Placement Y coordinate in natural-image pixels."),
    ]


class PlacementResponse(BaseModel):
    """Result of a placement-point operation (rescale-by-depth, smart-paste).

    Both routes recompute the object's size/position the same way -- depth
    at the placement point drives ``scale_factor`` -- and return this same
    shape; only the caller-facing route and its log messages differ.
    """

    object_uuid: Annotated[str, Field(description="Server-generated UUID for this object.")]
    session_id: Annotated[str, Field(description="Session UID.")]
    object_id: Annotated[int, Field(ge=0, description="Zero-based integer id within the session.")]
    source_average_depth: Annotated[
        float,
        Field(description="Object average depth before this placement operation."),
    ]
    target_depth: Annotated[
        float,
        Field(description="Sampled uint8 depth at the placement point."),
    ]
    scale_factor: Annotated[
        float,
        Field(description="Applied scale factor (target_depth / source_average_depth)."),
    ]
    display_scale: Annotated[
        float,
        Field(description="UI display scale vs original cutout size after this placement operation."),
    ]
    cutout_bounds: Annotated[
        CutoutBounds | None,
        Field(default=None, description="Logical display bounds (base alpha bbox scaled by display_scale)."),
    ]
