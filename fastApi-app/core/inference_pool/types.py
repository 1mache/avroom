from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class JobKind(str, Enum):
    """Supported inference job kinds dispatched to workers or inline execution."""

    SEGMENT = "segment"
    INPAINT = "inpaint"
    CLICK = "click"
    RESCALE_BY_DEPTH = "rescale_by_depth"
    GENERATE_3D = "generate_3d"
    NOVEL_VIEW = "novel_view"
    SHUTDOWN = "shutdown"


@dataclass(frozen=True)
class JobRequest:
    """Picklable inference job submitted to a worker or executed inline."""

    job_id: str
    kind: JobKind
    storage_dir: str
    image_id: str | None = None
    mask_id: str | None = None
    x: int | None = None
    y: int | None = None
    object_uuid: str | None = None
    cutout_path: str | None = None
    elevation_deg: float | None = None
    azimuth_deg: float | None = None
    relative_elevation_deg: float | None = None
    radius: float | None = None
    options: dict[str, Any] | None = None


@dataclass
class JobResult:
    """Outcome of one inference job."""

    job_id: str
    ok: bool
    error: str | None = None
    background_bytes: bytes | None = None
    cutout_bytes: bytes | None = None
    image_format: str | None = None
    candidates: list[tuple[str, bytes]] | None = None
    object_uuid: str | None = None
    session_id: str | None = None
    object_id: int | None = None
    source_average_depth: float | None = None
    target_depth: float | None = None
    scale_factor: float | None = None
    glb_bytes: bytes | None = None
    novel_view_bgra: Any | None = field(default=None, repr=False)
