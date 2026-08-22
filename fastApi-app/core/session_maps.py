from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable

import numpy as np

from core.avroom_package import load_avroom_attr
from core.depth_cache import content_hash_for_bytes, get_or_compute_depth, load_depth_map
from core.inference_lock import inference_session
from core.normal_cache import load_normal_map, warm_normals_for_session
from core.image_processing import load_canvas_bytes
from settings import get_normal_map_enabled

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WarmSessionMapsResult:
    """Outcome of ensuring depth and normal maps exist for the current canvas."""

    session_id: str
    content_hash: str
    depth_cache_hit: bool
    normal_cache_hit: bool | None


def warm_session_maps(
    base_dir: Path,
    session_id: str,
    map_normals_from_bytes: Callable[[bytes], np.ndarray],
) -> WarmSessionMapsResult:
    """Ensure depth (and optionally normal) maps exist for the session canvas.

    Uses the same canvas bytes and cache keys as segment/inpaint/rescale. Cache
    hits return immediately without reloading models.
    """
    image_bytes = load_canvas_bytes(image_id=session_id, base_dir=base_dir)
    content_hash = content_hash_for_bytes(image_bytes)
    depth_cache_hit = load_depth_map(base_dir, session_id, content_hash) is not None

    logger.info(
        "Session map warm start: session_id=%s content_hash=%s depth_hit=%s",
        session_id,
        content_hash[:12],
        depth_cache_hit,
    )

    with inference_session():
        segmentor = load_avroom_attr("ObjectSegmentor")()
        get_or_compute_depth(
            base_dir,
            session_id,
            image_bytes,
            segmentor.depth.map_depth,
        )

    normal_cache_hit: bool | None = None
    if get_normal_map_enabled():
        normal_cache_hit = load_normal_map(base_dir, session_id, content_hash) is not None
        warm_normals_for_session(
            base_dir,
            session_id,
            image_bytes,
            map_normals_from_bytes=map_normals_from_bytes,
        )
    else:
        logger.info("Session normal-map warm skipped: NORMAL_MAP=false session_id=%s", session_id)

    logger.info(
        "Session map warm complete: session_id=%s content_hash=%s depth_hit=%s normal_hit=%s",
        session_id,
        content_hash[:12],
        depth_cache_hit,
        normal_cache_hit,
    )
    return WarmSessionMapsResult(
        session_id=session_id,
        content_hash=content_hash,
        depth_cache_hit=depth_cache_hit,
        normal_cache_hit=normal_cache_hit,
    )
