from __future__ import annotations

"""Filesystem cache helpers for temporary segmentation candidates."""

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def mask_id_from_index(index: int) -> str:
    """Return stable public mask id for candidate order returned by SAM."""

    return str(index)


def refined_mask_path(base_dir: Path, image_id: str, mask_id: str) -> Path:
    """Return path used to cache one refined mask as a NumPy array."""

    return base_dir / f"{image_id}_mask_{mask_id}_refined.npy"


def cutout_path(base_dir: Path, image_id: str, mask_id: str) -> Path:
    """Return path used to cache one candidate cutout preview PNG."""

    return base_dir / f"{image_id}_mask_{mask_id}_cutout.png"


def save_candidate(
    base_dir: Path,
    image_id: str,
    mask_id: str,
    refined_mask: np.ndarray,
    cutout_bytes: bytes,
) -> None:
    """Persist one segmentation candidate for later user selection."""

    base_dir.mkdir(parents=True, exist_ok=True)
    np.save(refined_mask_path(base_dir, image_id, mask_id), refined_mask)
    cutout_path(base_dir, image_id, mask_id).write_bytes(cutout_bytes)
    logger.debug(
        "Cached mask candidate: image_id=%s mask_id=%s mask_shape=%s cutout_bytes=%d",
        image_id,
        mask_id,
        refined_mask.shape,
        len(cutout_bytes),
    )


def load_refined_mask(base_dir: Path, image_id: str, mask_id: str) -> np.ndarray:
    """Load cached refined mask selected by the user."""

    path = refined_mask_path(base_dir, image_id, mask_id)
    if not path.exists():
        raise FileNotFoundError(f"Cached mask not found for image_id='{image_id}', mask_id='{mask_id}'")
    mask = np.load(path)
    logger.debug(
        "Loaded cached refined mask: image_id=%s mask_id=%s path=%s shape=%s",
        image_id,
        mask_id,
        path,
        mask.shape,
    )
    return mask


def load_cutout_bytes(base_dir: Path, image_id: str, mask_id: str) -> bytes:
    """Load cached candidate cutout PNG selected by the user."""

    path = cutout_path(base_dir, image_id, mask_id)
    if not path.exists():
        raise FileNotFoundError(f"Cached cutout not found for image_id='{image_id}', mask_id='{mask_id}'")
    return path.read_bytes()


def delete_candidates(base_dir: Path, image_id: str) -> None:
    """Delete all temporary candidate files for one image id.

    Only files with the candidate naming pattern are removed, so final
    background/cutout outputs and original uploads are left untouched.
    """

    removed = 0
    for path in base_dir.glob(f"{image_id}_mask_*_refined.npy"):
        path.unlink(missing_ok=True)
        removed += 1
    for path in base_dir.glob(f"{image_id}_mask_*_cutout.png"):
        path.unlink(missing_ok=True)
        removed += 1
    logger.debug("Deleted mask candidates: image_id=%s removed=%d", image_id, removed)
