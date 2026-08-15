from __future__ import annotations

import math

import numpy as np

# Pad the mask bounding box by this fraction of its width/height on each side.
INPAINT_VERIFY_CROP_PAD_RATIO: float = 0.25


def crop_around_mask(
    image: np.ndarray,
    mask: np.ndarray,
    pad_ratio: float = INPAINT_VERIFY_CROP_PAD_RATIO,
) -> np.ndarray:
    """Return a BGR crop around the mask bbox, padded then clamped to the image.

    Empty masks fall back to the full image so CLIP still receives pixels.
    """
    h, w = image.shape[:2]
    mask_bool = _mask_bool(mask)
    if not mask_bool.any():
        return image

    rows = np.any(mask_bool, axis=1)
    cols = np.any(mask_bool, axis=0)
    y0, y1 = int(np.argmax(rows)), int(h - np.argmax(rows[::-1]))
    x0, x1 = int(np.argmax(cols)), int(w - np.argmax(cols[::-1]))

    box_h = max(y1 - y0, 1)
    box_w = max(x1 - x0, 1)
    pad_y = max(1, int(math.ceil(box_h * pad_ratio)))
    pad_x = max(1, int(math.ceil(box_w * pad_ratio)))

    y0 = max(0, y0 - pad_y)
    x0 = max(0, x0 - pad_x)
    y1 = min(h, y1 + pad_y)
    x1 = min(w, x1 + pad_x)
    return image[y0:y1, x0:x1]


def _mask_bool(mask: np.ndarray) -> np.ndarray:
    if mask.ndim == 3:
        mask = mask[:, :, 0]
    if mask.dtype == np.uint8 or (mask.size and float(mask.max()) > 1.0):
        return mask > 127
    return mask > 0.5
