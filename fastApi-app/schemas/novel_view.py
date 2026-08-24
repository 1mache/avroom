from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from avroom_object_removal.ai_engines.novel_view import (
    AzimuthDirection,
    ElevationDirection,
    ZoomDirection,
)

from schemas.common import CutoutBounds


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
