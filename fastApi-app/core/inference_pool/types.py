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
    SMART_PASTE = "smart_paste"
    GENERATE_3D = "generate_3d"
    NOVEL_VIEW = "novel_view"
    VALIDATE_CONTENT = "validate_content"
    CALIBRATE_CAMERA = "calibrate_camera"
    MAP_NORMALS = "map_normals"
    WARM_SESSION_MAPS = "warm_session_maps"
    DEBUG_DEPTH_MAP = "debug_depth_map"
    DEBUG_NORMAL_MAP = "debug_normal_map"
    DEBUG_SAM_EVERYTHING = "debug_sam_everything"
    DEBUG_AUTO_MASK_PICK = "debug_auto_mask_pick"
    DEBUG_INPAINT_VERIFY = "debug_inpaint_verify"
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
    mesh_path: str | None = None
    elevation_deg: float | None = None
    azimuth_deg: float | None = None
    relative_elevation_deg: float | None = None
    radius: float | None = None
    options: dict[str, Any] | None = None
    exclude_mask_ids: tuple[str, ...] | None = None
    image_bytes: bytes | None = None
    verify: str | None = None


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
    display_scale: float | None = None
    glb_bytes: bytes | None = None
    novel_view_bgra: Any | None = field(default=None, repr=False)
    validation_ok: bool | None = None
    validation_checks: dict[str, bool] | None = None
    validation_scores: dict[str, float] | None = None
    validation_messages: tuple[str, ...] | None = None
    camera_calib_gravity: tuple[float, float, float] | None = None
    camera_calib_roll_deg: float | None = None
    camera_calib_pitch_deg: float | None = None
    camera_calib_fx: float | None = None
    camera_calib_fy: float | None = None
    camera_calib_cx: float | None = None
    camera_calib_cy: float | None = None
    camera_calib_confidence: float | None = None
    camera_calib_camera_model: str | None = None
    normal_map: Any | None = field(default=None, repr=False)
    debug_png_bytes: bytes | None = None
    debug_mask_count: int | None = None
    debug_payload: dict[str, Any] | None = None
    warm_content_hash: str | None = None
    depth_cache_hit: bool | None = None
    normal_cache_hit: bool | None = None
