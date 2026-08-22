from __future__ import annotations

import logging

import cv2
import numpy as np

from schemas.image import CutoutBounds

logger = logging.getLogger(__name__)


def extract_cutout_bounds_from_png_bytes(image_bytes: bytes) -> CutoutBounds | None:
    """Return tight alpha bounds for a BGRA cutout PNG."""

    decoded = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if decoded is None:
        logger.warning("Failed to decode cutout bytes for bounds extraction")
        return None

    if decoded.ndim != 3 or decoded.shape[2] < 4:
        logger.warning("Cutout image missing alpha channel: shape=%s", decoded.shape)
        height, width = decoded.shape[:2]
        return CutoutBounds(
            left=0,
            top=0,
            right=width,
            bottom=height,
            natural_width=width,
            natural_height=height,
        )

    alpha = decoded[:, :, 3]
    non_zero_points = cv2.findNonZero(alpha)
    height, width = alpha.shape

    if non_zero_points is None:
        return CutoutBounds(
            left=0,
            top=0,
            right=width,
            bottom=height,
            natural_width=width,
            natural_height=height,
        )

    x, y, w, h = cv2.boundingRect(non_zero_points)
    return CutoutBounds(
        left=int(x),
        top=int(y),
        right=int(x + w),
        bottom=int(y + h),
        natural_width=width,
        natural_height=height,
    )


def scale_cutout_bounds(bounds: CutoutBounds, scale_factor: float) -> CutoutBounds:
    """Grow or shrink *bounds* about its center by *scale_factor*."""
    grow_x = ((bounds.right - bounds.left) * (scale_factor - 1.0)) / 2.0
    grow_y = ((bounds.bottom - bounds.top) * (scale_factor - 1.0)) / 2.0
    return CutoutBounds(
        left=int(round(bounds.left - grow_x)),
        top=int(round(bounds.top - grow_y)),
        right=int(round(bounds.right + grow_x)),
        bottom=int(round(bounds.bottom + grow_y)),
        natural_width=bounds.natural_width,
        natural_height=bounds.natural_height,
    )
