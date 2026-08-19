from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

# Pad the mask bounding box by this fraction of its width/height on each side.
INPAINT_VERIFY_CROP_PAD_RATIO: float = 0.25
GEMINI_CROP_PAD_RATIO: float = 0.35
MIN_VERIFY_CROP_PX: int = 256
MIN_VERIFY_CROP_FRAC: float = 0.25

_OUTLINE_COLOR_BGR: tuple[int, int, int] = (255, 255, 0)


@dataclass(frozen=True)
class CropWindow:
    """Axis-aligned slice of a full image used for verify crops."""

    y0: int
    y1: int
    x0: int
    x1: int

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    @property
    def width(self) -> int:
        return self.x1 - self.x0


def crop_around_mask(
    image: np.ndarray,
    mask: np.ndarray,
    pad_ratio: float = INPAINT_VERIFY_CROP_PAD_RATIO,
) -> np.ndarray:
    """Return a BGR crop around the mask bbox, padded then clamped to the image.

    Empty masks fall back to the full image so CLIP still receives pixels.
    """
    window = mask_crop_window(
        mask,
        pad_ratio=pad_ratio,
        min_side_px=0,
        min_side_frac=0.0,
    )
    return crop_with_window(image, window)


def mask_crop_window(
    mask: np.ndarray,
    pad_ratio: float = GEMINI_CROP_PAD_RATIO,
    min_side_px: int = MIN_VERIFY_CROP_PX,
    min_side_frac: float = MIN_VERIFY_CROP_FRAC,
) -> CropWindow:
    """Compute one padded window from the mask bbox, optionally enforcing a minimum size."""
    h, w = mask.shape[:2]
    mask_bool = _mask_bool(mask)
    y0, y1, x0, x1 = _mask_bbox(mask_bool, h, w)

    box_h = max(y1 - y0, 1)
    box_w = max(x1 - x0, 1)
    pad_y = max(1, int(math.ceil(box_h * pad_ratio)))
    pad_x = max(1, int(math.ceil(box_w * pad_ratio)))

    y0 = max(0, y0 - pad_y)
    x0 = max(0, x0 - pad_x)
    y1 = min(h, y1 + pad_y)
    x1 = min(w, x1 + pad_x)

    min_side = 0
    if min_side_px > 0 or min_side_frac > 0:
        min_side = max(min_side_px, int(min(h, w) * min_side_frac))

    if min_side > 0:
        y0, y1 = _expand_axis(y0, y1, h, min_side)
        x0, x1 = _expand_axis(x0, x1, w, min_side)

    return CropWindow(y0=y0, y1=y1, x0=x0, x1=x1)


def crop_with_window(image: np.ndarray, window: CropWindow) -> np.ndarray:
    """Slice ``image`` to ``window``."""
    return image[window.y0 : window.y1, window.x0 : window.x1]


def mask_pixels_in_window(mask: np.ndarray, window: CropWindow) -> int:
    """Foreground pixel count inside ``window``."""
    mask_bool = _mask_bool(mask)
    region = mask_bool[window.y0 : window.y1, window.x0 : window.x1]
    return int(np.count_nonzero(region))


def draw_mask_outline(
    crop_bgr: np.ndarray,
    mask: np.ndarray,
    window: CropWindow,
) -> np.ndarray:
    """Draw a cyan contour of the mask inside ``window`` on a copy of ``crop_bgr``."""
    out = crop_bgr.copy()
    mask_bool = _mask_bool(mask)
    local = (mask_bool[window.y0 : window.y1, window.x0 : window.x1]).astype(np.uint8) * 255
    if not local.any():
        return out
    contours, _ = cv2.findContours(local, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        cv2.drawContours(out, contours, -1, _OUTLINE_COLOR_BGR, thickness=2)
    return out


def build_verify_crops(
    original: np.ndarray,
    candidate: np.ndarray,
    mask: np.ndarray,
    *,
    pad_ratio: float = GEMINI_CROP_PAD_RATIO,
    min_side_px: int = MIN_VERIFY_CROP_PX,
    min_side_frac: float = MIN_VERIFY_CROP_FRAC,
) -> tuple[np.ndarray, np.ndarray, CropWindow]:
    """Return original crop, outlined candidate crop, and the shared window."""
    window = mask_crop_window(mask, pad_ratio, min_side_px, min_side_frac)
    original_crop = crop_with_window(original, window)
    candidate_crop = crop_with_window(candidate, window)
    outlined = draw_mask_outline(candidate_crop, mask, window)
    return original_crop, outlined, window


def _mask_bool(mask: np.ndarray) -> np.ndarray:
    if mask.ndim == 3:
        mask = mask[:, :, 0]
    if mask.dtype == np.uint8 or (mask.size and float(mask.max()) > 1.0):
        return mask > 127
    return mask > 0.5


def _mask_bbox(mask_bool: np.ndarray, h: int, w: int) -> tuple[int, int, int, int]:
    if not mask_bool.any():
        return 0, h, 0, w
    rows = np.any(mask_bool, axis=1)
    cols = np.any(mask_bool, axis=0)
    y0 = int(np.argmax(rows))
    y1 = int(h - np.argmax(rows[::-1]))
    x0 = int(np.argmax(cols))
    x1 = int(w - np.argmax(cols[::-1]))
    return y0, y1, x0, x1


def _expand_axis(start: int, end: int, limit: int, min_size: int) -> tuple[int, int]:
    """Grow ``[start, end)`` symmetrically to at least ``min_size``, clamped to ``[0, limit)``."""
    size = end - start
    if size >= min_size:
        return start, end
    center = (start + end) // 2
    half = min_size // 2
    new_start = max(0, center - half)
    new_end = min(limit, new_start + min_size)
    new_start = max(0, new_end - min_size)
    return new_start, new_end
