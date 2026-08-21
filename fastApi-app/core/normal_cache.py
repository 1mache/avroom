from __future__ import annotations

"""Filesystem cache for session normal maps keyed by canvas content hash."""

import logging
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

from core.depth_cache import content_hash_for_bytes

logger = logging.getLogger(__name__)


def normal_map_path(base_dir: Path, session_id: str, content_hash: str) -> Path:
    """Return canonical path for a cached normal map NumPy array."""
    return base_dir / f"{session_id}_normal_{content_hash}.npy"


def load_normal_map(base_dir: Path, session_id: str, content_hash: str) -> np.ndarray | None:
    """Load a cached normal map if present, otherwise return ``None``."""
    path = normal_map_path(base_dir, session_id, content_hash)
    if not path.exists():
        return None
    normals = np.load(path)
    logger.info(
        "Normal cache hit: session_id=%s content_hash=%s shape=%s",
        session_id,
        content_hash[:12],
        normals.shape,
    )
    return normals


def _validate_normals(normals: np.ndarray) -> np.ndarray:
    """Require float HxWx3; cast to float32 when needed."""
    arr = np.asarray(normals)
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError(f"Normal map must be HxWx3, got shape={arr.shape}")
    if not np.issubdtype(arr.dtype, np.floating):
        raise ValueError(f"Normal map must be floating dtype, got {arr.dtype}")
    return arr.astype(np.float32, copy=False)


def save_normal_map(
    base_dir: Path,
    session_id: str,
    content_hash: str,
    normals: np.ndarray,
) -> Path:
    """Persist a normal map and return the written path."""
    validated = _validate_normals(normals)
    path = normal_map_path(base_dir, session_id, content_hash)
    np.save(path, validated)
    logger.info(
        "Normal cache saved: session_id=%s content_hash=%s path=%s shape=%s",
        session_id,
        content_hash[:12],
        path,
        validated.shape,
    )
    return path


def delete_session_normal_maps(base_dir: Path, session_id: str) -> int:
    """Remove all cached normal maps for a session. Returns files removed."""
    removed = 0
    for path in base_dir.glob(f"{session_id}_normal_*.npy"):
        path.unlink(missing_ok=True)
        removed += 1
    if removed:
        logger.debug("Deleted normal cache files: session_id=%s count=%d", session_id, removed)
    return removed


def get_or_compute_normals(
    base_dir: Path,
    session_id: str,
    image_bytes: bytes,
    map_normals_fn: Callable[[np.ndarray], np.ndarray],
) -> tuple[np.ndarray, str]:
    """Load cached normals for session+content or compute, save, and return them.

    Args:
        base_dir: Image storage directory.
        session_id: Session UID.
        image_bytes: Raw canvas bytes (original upload or cumulative background).
        map_normals_fn: Callable that maps a decoded BGR image to float32 HxWx3.

    Returns:
        Tuple of ``(normals, content_hash)``.
    """
    content_hash = content_hash_for_bytes(image_bytes)
    cached = load_normal_map(base_dir, session_id, content_hash)
    if cached is not None:
        return cached, content_hash

    logger.info(
        "Normal cache miss: session_id=%s content_hash=%s — computing",
        session_id,
        content_hash[:12],
    )
    decoded = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if decoded is None:
        raise ValueError("Could not decode image bytes into an image array for normal mapping.")

    normals = _validate_normals(map_normals_fn(decoded))
    save_normal_map(base_dir, session_id, content_hash, normals)
    return normals, content_hash


def warm_normals_for_session(
    base_dir: Path,
    session_id: str,
    image_bytes: bytes,
    map_normals_from_bytes: Callable[[bytes], np.ndarray],
) -> str:
    """Ensure a normal map exists for ``image_bytes``; skip compute on cache hit.

    ``map_normals_from_bytes`` should run Metric3D via the inference pool (takes
    raw image bytes, returns float32 HxWx3). Returns the content hash used.
    """
    content_hash = content_hash_for_bytes(image_bytes)
    if load_normal_map(base_dir, session_id, content_hash) is not None:
        return content_hash

    logger.info(
        "Normal cache warm: session_id=%s content_hash=%s — computing via pool",
        session_id,
        content_hash[:12],
    )
    normals = _validate_normals(map_normals_from_bytes(image_bytes))
    save_normal_map(base_dir, session_id, content_hash, normals)
    return content_hash
