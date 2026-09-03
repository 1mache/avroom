from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from schemas.common import CutoutBounds

JobKind = Literal["segment", "inpaint", "erase", "generate_3d"]
JobStatus = Literal["queued", "running", "done", "failed", "conflict"]


class JobInfo(BaseModel):
    """One durable queued-work row, as returned to the owning client."""

    job_id: Annotated[str, Field(description="Server-generated job id.")]
    session_id: Annotated[str, Field(description="Session UID this job belongs to.")]
    kind: Annotated[JobKind, Field(description="What kind of work this job runs.")]
    status: Annotated[JobStatus, Field(description="Current lifecycle state.")]
    error: Annotated[
        str | None,
        Field(default=None, description="Failure/conflict message, set only for those statuses."),
    ]
    created_at: Annotated[str, Field(description="ISO-8601 UTC timestamp the job was submitted.")]
    object_id: Annotated[
        int | None,
        Field(
            default=None,
            description="Target object id, present only for generate_3d jobs (from payload.object_id).",
        ),
    ]
    verify: Annotated[
        Literal["manual", "auto"] | None,
        Field(
            default=None,
            description="Verify mode the job was submitted with, present only for segment jobs.",
        ),
    ]


class JobSubmitResponse(BaseModel):
    """Response for job-submitting routes: segment, inpaint, erase, generate_3d."""

    job_id: Annotated[str, Field(description="Id of the newly queued job. Poll via GET /jobs/{job_id}.")]


class SegmentMaskResult(BaseModel):
    """One selectable mask candidate from a finished segment job."""

    mask_id: Annotated[str, Field(pattern=r"^\d+$", description="Cached refined-mask/cutout candidate id.")]
    cutout_b64: Annotated[str, Field(description="Base64-encoded BGRA cutout preview for this candidate.")]
    format: Annotated[str, Field(description="Preview image format, currently 'png'.")]
    cutout_bounds: Annotated[
        CutoutBounds | None,
        Field(default=None, description="Tight visible-object bounds inside this cutout PNG."),
    ]


class JobDetailResponse(JobInfo):
    """One job with its inflated result, for GET /jobs/{job_id}.

    `masks` is populated only for a `done` segment job (inflated on read from
    the cached candidate PNGs on disk via `payload`/`result`'s mask ids —
    never stored as base64 in the row itself).
    """

    masks: Annotated[
        list[SegmentMaskResult] | None,
        Field(default=None, description="Selectable candidates, present only for a done segment job."),
    ]


class InpaintJobRequest(BaseModel):
    """Request payload for POST /images/segment and POST /images/inpaint (submit)."""

    image_id: Annotated[str, Field(description="Session UID.")]


class SegmentJobRequest(BaseModel):
    """Request payload for POST /images/segment."""

    image_id: Annotated[str, Field(description="Session UID.")]
    x: Annotated[int, Field(ge=0, description="Click X coordinate in pixels from the left edge.")]
    y: Annotated[int, Field(ge=0, description="Click Y coordinate in pixels from the top edge.")]
    options: Annotated[
        dict[str, Any] | None,
        Field(default=None, description="Optional processing options, passed through to the pipeline."),
    ]


class SubmitInpaintRequest(BaseModel):
    """Request payload for POST /images/inpaint (submit)."""

    image_id: Annotated[str, Field(description="Session UID.")]
    mask_id: Annotated[
        str,
        Field(min_length=1, pattern=r"^\d+$", description="Selected cached mask candidate id."),
    ]
    from_job_id: Annotated[
        str | None,
        Field(
            default=None,
            description="Id of the segment job this mask came from, so its row is consumed atomically.",
        ),
    ]
    generate_3d: Annotated[
        bool,
        Field(
            default=False,
            description="When true, queue 3D generation for the new object after cutout completes.",
        ),
    ]


class SubmitEraseRequest(BaseModel):
    """Request payload for POST /images/erase (submit)."""

    image_id: Annotated[str, Field(description="Session UID.")]
    mask_b64: Annotated[
        str,
        Field(min_length=1, description="Base64-encoded PNG erase mask (uint8 HxW, 255=erase)."),
    ]


class Generate3DJobRequest(BaseModel):
    """Request payload for POST /3d/test-3d (submit)."""

    uid: Annotated[str, Field(min_length=1, description="Session UID.")]
    object_id: Annotated[int, Field(ge=0, description="Object id within the session to generate 3D from.")] = 0
