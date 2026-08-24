from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from schemas.common import VerifyMode


class BatchBoxSource(BaseModel):
    """Discover furniture-like SAM masks whose centroid falls in a box."""

    kind: Literal["box"] = "box"
    x0: Annotated[int, Field(ge=0)]
    y0: Annotated[int, Field(ge=0)]
    x1: Annotated[int, Field(ge=0)]
    y1: Annotated[int, Field(ge=0)]


class BatchClickPoint(BaseModel):
    """One natural-image click for batch auto-segment."""

    x: Annotated[int, Field(ge=0)]
    y: Annotated[int, Field(ge=0)]


class BatchClicksSource(BaseModel):
    """Auto-segment each click; skip points that yield no viable mask."""

    kind: Literal["clicks"] = "clicks"
    points: Annotated[list[BatchClickPoint], Field(min_length=1)]


class BatchObjectsSource(BaseModel):
    """Generate 3D only for existing session objects."""

    kind: Literal["objects"] = "objects"
    uuids: Annotated[list[str], Field(min_length=1)]


class BatchRequest(BaseModel):
    """Bulk discover / peel / GLB for one session. ``verify`` is always auto."""

    source: Annotated[
        BatchBoxSource | BatchClicksSource | BatchObjectsSource,
        Field(discriminator="kind"),
    ]
    then: Annotated[
        list[Literal["inpaint", "generate_3d"]],
        Field(default_factory=lambda: ["inpaint", "generate_3d"]),
    ]
    verify: Annotated[
        VerifyMode,
        Field(default=VerifyMode.AUTO, description="Ignored; batch always uses auto."),
    ] = VerifyMode.AUTO


class BatchObjectResult(BaseModel):
    """Per-object outcome inside a batch."""

    object_id: Annotated[int | None, Field(default=None)]
    object_uuid: Annotated[str | None, Field(default=None)]
    status: Annotated[str, Field(description="created, skipped, or glb_only.")]
    error: Annotated[str | None, Field(default=None)]


class BatchGlbResult(BaseModel):
    """Per-object GLB outcome after all peels."""

    object_id: Annotated[int, Field(ge=0)]
    ok: Annotated[bool, Field()]
    error: Annotated[str | None, Field(default=None)]


class BatchResponse(BaseModel):
    """Result of POST /images/{uid}/batch."""

    batch_id: Annotated[str, Field()]
    image_id: Annotated[str, Field()]
    objects: Annotated[list[BatchObjectResult], Field()]
    glbs: Annotated[list[BatchGlbResult], Field()]
    last_changed: Annotated[str, Field()]
