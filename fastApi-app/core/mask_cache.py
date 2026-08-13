from __future__ import annotations

"""Filesystem cache helpers for temporary segmentation candidates."""

import logging
import re
from pathlib import Path
from typing import AbstractSet

import numpy as np

from core.object_storage import remove_file

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


_REFINED_MASK_PATTERN = re.compile(r"^.+_mask_(?P<mask_id>.+)_refined\.npy$")
_CUTOUT_MASK_PATTERN = re.compile(r"^.+_mask_(?P<mask_id>.+)_cutout\.png$")


def _mask_id_from_candidate_path(path: Path, pattern: re.Pattern[str]) -> str | None:
    """Extract the public mask id embedded in one candidate filename."""

    match = pattern.match(path.name)
    if match is None:
        return None
    return match.group("mask_id")


def delete_candidate(base_dir: Path, image_id: str, mask_id: str) -> None:
    """Delete one temporary candidate pair for the given mask id."""

    removed = remove_file(refined_mask_path(base_dir, image_id, mask_id))
    removed += remove_file(cutout_path(base_dir, image_id, mask_id))
    logger.debug(
        "Deleted mask candidate: image_id=%s mask_id=%s removed=%d",
        image_id,
        mask_id,
        removed,
    )


def _delete_unpinned(
    base_dir: Path,
    glob_pattern: str,
    name_pattern: re.Pattern[str],
    excluded: AbstractSet[str],
) -> int:
    """Delete candidate files matching *glob_pattern* unless their mask id is pinned."""

    removed = 0
    for path in base_dir.glob(glob_pattern):
        mask_id = _mask_id_from_candidate_path(path, name_pattern)
        if mask_id is not None and mask_id in excluded:
            continue
        path.unlink(missing_ok=True)
        removed += 1
    return removed


def delete_candidates(
    base_dir: Path,
    image_id: str,
    exclude_mask_ids: AbstractSet[str] | None = None,
) -> None:
    """Delete temporary candidate files for one image id.

    Only files with the candidate naming pattern are removed, so final
    background/cutout outputs and original uploads are left untouched.
    Pinned mask ids are skipped so in-flight inpaints keep their files.
    """

    excluded = exclude_mask_ids or set()
    removed = _delete_unpinned(base_dir, f"{image_id}_mask_*_refined.npy", _REFINED_MASK_PATTERN, excluded)
    removed += _delete_unpinned(base_dir, f"{image_id}_mask_*_cutout.png", _CUTOUT_MASK_PATTERN, excluded)
    logger.debug(
        "Deleted mask candidates: image_id=%s removed=%d excluded=%s",
        image_id,
        removed,
        sorted(excluded),
    )
