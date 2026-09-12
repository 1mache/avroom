"""Classify a cutout as planar (painting/TV) vs volumetric (furniture) via CLIP.

Run once after object removal / import. The result is persisted as ``is_3d``
on object metadata so rotate and smart-rotate can pick CSS 3D vs mesh novel-view.
"""

from __future__ import annotations

import logging
from typing import Protocol

import numpy as np
from PIL import Image

from .cutout_selector import _crop_on_gray

logger = logging.getLogger(__name__)

# Softmax over both groups together, then compare group means. When the
# means are within this band, prefer volumetric so we keep today's mesh path
# rather than silently locking a chair into CSS tilt.
TIE_BAND = 0.1

VOLUMETRIC_LABELS: tuple[str, ...] = (
    "a three-dimensional piece of furniture",
    "a chair, sofa, table, lamp, or sculpture with depth",
)

PLANAR_LABELS: tuple[str, ...] = (
    "a flat painting or poster on a wall",
    "a television screen, photograph, or wall art",
    "a mirror or whiteboard",
)


class LabelScorer(Protocol):
    """Minimal CLIP surface for batched label scoring."""

    def score_labels(self, pil_image: Image.Image, labels: tuple[str, ...]) -> dict[str, float]:
        """Return a softmax distribution over ``labels``."""


def classify_object_is_3d(
    cutout_bgra: np.ndarray,
    *,
    scorer: LabelScorer,
    tie_band: float = TIE_BAND,
) -> bool:
    """Return ``True`` when the cutout looks volumetric (furniture), else planar.

    Crops the cutout onto a gray background (same as mask-pick CLIP) before
    scoring. Empty / fully-transparent cutouts default to volumetric.
    """
    crop = _crop_on_gray(cutout_bgra)
    if crop is None:
        logger.warning("Object shape classify: empty cutout crop; defaulting is_3d=True")
        return True

    labels = VOLUMETRIC_LABELS + PLANAR_LABELS
    scores = scorer.score_labels(crop, labels)
    volumetric_mean = sum(scores[label] for label in VOLUMETRIC_LABELS) / len(VOLUMETRIC_LABELS)
    planar_mean = sum(scores[label] for label in PLANAR_LABELS) / len(PLANAR_LABELS)

    if abs(volumetric_mean - planar_mean) <= tie_band:
        is_3d = True
        decision = "tie->volumetric"
    else:
        is_3d = volumetric_mean > planar_mean
        decision = "volumetric" if is_3d else "planar"

    logger.info(
        "Object shape classify: decision=%s volumetric_mean=%.3f planar_mean=%.3f",
        decision,
        volumetric_mean,
        planar_mean,
    )
    return is_3d


def classify_object_is_3d_from_png_bytes(
    cutout_png: bytes,
    *,
    scorer: LabelScorer,
    tie_band: float = TIE_BAND,
) -> bool:
    """Decode a BGRA PNG cutout and classify it."""
    import cv2

    array = np.frombuffer(cutout_png, dtype=np.uint8)
    bgra = cv2.imdecode(array, cv2.IMREAD_UNCHANGED)
    if bgra is None:
        logger.warning("Object shape classify: PNG decode failed; defaulting is_3d=True")
        return True
    if bgra.ndim != 3 or bgra.shape[2] < 4:
        # No alpha channel — treat as opaque BGR and synthesize full alpha.
        if bgra.ndim == 2:
            bgra = cv2.cvtColor(bgra, cv2.COLOR_GRAY2BGRA)
        else:
            bgr = bgra[:, :, :3]
            alpha = np.full(bgr.shape[:2], 255, dtype=np.uint8)
            bgra = np.dstack([bgr, alpha])
    return classify_object_is_3d(bgra, scorer=scorer, tie_band=tie_band)
