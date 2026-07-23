from __future__ import annotations

"""Filesystem cache for session depth maps keyed by canvas content hash."""

import hashlib
import logging
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)


def content_hash_for_bytes(image_bytes: bytes) -> str:
    """Return SHA-256 hex digest of raw image/canvas bytes."""
    return hashlib.sha256(image_bytes).hexdigest()


def depth_map_path(base_dir: Path, session_id: str, content_hash: str) -> Path:
    """Return canonical path for a cached depth map NumPy array."""
    return base_dir / f"{session_id}_depth_{content_hash}.npy"


def load_depth_map(base_dir: Path, session_id: str, content_hash: str) -> np.ndarray | None:
    """Load a cached depth map if present, otherwise return ``None``."""
    path = depth_map_path(base_dir, session_id, content_hash)
    if not path.exists():
        return None
    depth = np.load(path)
    logger.info(
        "Depth cache hit: session_id=%s content_hash=%s shape=%s",
        session_id,
        content_hash[:12],
        depth.shape,
    )
    return depth


def save_depth_map(
    base_dir: Path,
    session_id: str,
    content_hash: str,
    depth_map: np.ndarray,
) -> Path:
    """Persist a depth map and return the written path."""
    path = depth_map_path(base_dir, session_id, content_hash)
    np.save(path, depth_map)
    logger.info(
        "Depth cache saved: session_id=%s content_hash=%s path=%s shape=%s",
        session_id,
        content_hash[:12],
        path,
        depth_map.shape,
    )
    return path


def delete_session_depth_maps(base_dir: Path, session_id: str) -> int:
    """Remove all cached depth maps for a session. Returns files removed."""
    removed = 0
    for path in base_dir.glob(f"{session_id}_depth_*.npy"):
        path.unlink(missing_ok=True)
        removed += 1
    if removed:
        logger.debug("Deleted depth cache files: session_id=%s count=%d", session_id, removed)
    return removed


def compute_average_depth_over_mask(depth_map: np.ndarray, mask: np.ndarray) -> float:
    """Return mean uint8 depth inside ``mask > 0``, or ``0.0`` when empty."""
    if depth_map.ndim == 3:
        depth_map = depth_map[:, :, 0]

    mask_bool = mask > 0 if mask.dtype != bool else mask
    if mask.shape[:2] != depth_map.shape[:2]:
        mask_bool = cv2.resize(
            mask_bool.astype(np.uint8),
            (depth_map.shape[1], depth_map.shape[0]),
            interpolation=cv2.INTER_NEAREST,
        ) > 0

    pixels = depth_map[mask_bool]
    if pixels.size == 0:
        logger.warning("Average depth requested for empty mask — returning 0.0")
        return 0.0
    return float(np.mean(pixels))


def get_or_compute_depth(
    base_dir: Path,
    session_id: str,
    image_bytes: bytes,
    map_depth_fn: Callable[[np.ndarray], np.ndarray],
) -> tuple[np.ndarray, str]:
    """Load cached depth for session+content or compute, save, and return it.

    Args:
        base_dir: Image storage directory.
        session_id: Session UID.
        image_bytes: Raw canvas bytes (original upload or cumulative background).
        map_depth_fn: Callable that maps a decoded BGR image to a depth array.

    Returns:
        Tuple of ``(depth_map, content_hash)``.
    """
    content_hash = content_hash_for_bytes(image_bytes)
    cached = load_depth_map(base_dir, session_id, content_hash)
    if cached is not None:
        return cached, content_hash

    logger.info(
        "Depth cache miss: session_id=%s content_hash=%s — computing",
        session_id,
        content_hash[:12],
    )
    decoded = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if decoded is None:
        raise ValueError("Could not decode image bytes into an image array for depth mapping.")

    depth_map = map_depth_fn(decoded)
    save_depth_map(base_dir, session_id, content_hash, depth_map)
    return depth_map, content_hash
