from __future__ import annotations

import colorsys
import logging
from collections.abc import Sequence

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Golden-ratio conjugate: stepping hue by this fraction each time keeps
# consecutive colors visually far apart no matter how many masks there are.
_GOLDEN_RATIO_CONJUGATE = 0.618033988749895


def distinct_color(index: int) -> tuple[int, int, int]:
    """Return a deterministic, well-separated BGR color for mask ``index``.

    Hues are stepped by the golden-ratio conjugate so that colors stay
    visually distinct even across dozens of masks, and the same ``index``
    always maps to the same color across runs (unlike ``np.random`` colors).
    """
    hue = (index * _GOLDEN_RATIO_CONJUGATE) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 1.0)
    return (int(b * 255), int(g * 255), int(r * 255))


def colorize_depth(depth: np.ndarray, colormap: int | None = None) -> np.ndarray:
    """Normalize a depth map to uint8 and return a viewable BGR image.

    Args:
        depth: 2-D or 3-D depth array of any numeric dtype/range.
        colormap: An OpenCV ``cv2.COLORMAP_*`` constant, or ``None`` for a
            plain grayscale-as-BGR render.
    """
    arr = np.asarray(depth)
    if arr.ndim == 3:
        if arr.shape[2] == 3:
            gray_input = arr if arr.dtype == np.uint8 else arr.astype(np.uint8)
            arr = cv2.cvtColor(gray_input, cv2.COLOR_RGB2GRAY)
        else:
            arr = arr[:, :, 0]

    normalized = cv2.normalize(arr.astype(np.float32), None, 0, 255, cv2.NORM_MINMAX)
    normalized_u8 = normalized.astype(np.uint8)

    if colormap is None:
        return cv2.cvtColor(normalized_u8, cv2.COLOR_GRAY2BGR)
    return cv2.applyColorMap(normalized_u8, colormap)


def colorize_normals(normals: np.ndarray) -> np.ndarray:
    """Encode unit normals as a viewable BGR uint8 image for ``cv2.imencode``.

    Uses the standard Omnidata / Metric3D mapping ``(n + 1) / 2 * 255`` on
    ``(nx, ny, nz)``, then converts to OpenCV BGR so PNG bytes display in a
    browser with ``R=nx, G=ny, B=nz`` (canvas ``getImageData`` can recover
    ``n = rgb/255*2-1``).

    Args:
        normals: ``float`` array of shape ``(H, W, 3)`` with values roughly
            in ``[-1, 1]``.
    """
    arr = np.asarray(normals, dtype=np.float32)
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError(f"colorize_normals expects HxWx3, got shape={arr.shape}")

    rgb_u8 = np.clip((arr + 1.0) * 0.5 * 255.0, 0, 255).astype(np.uint8)
    return cv2.cvtColor(rgb_u8, cv2.COLOR_RGB2BGR)


def normals_from_vis_bgr(bgr: np.ndarray) -> np.ndarray:
    """Inverse of :func:`colorize_normals` for OpenCV-loaded debug images.

    Args:
        bgr: BGR uint8 image produced by :func:`colorize_normals` (or
            ``cv2.imdecode`` of that PNG).

    Returns:
        ``float32`` HxWx3 approximately unit normals (quantization noise from
        8-bit encoding; re-normalize if you need unit length).
    """
    arr = np.asarray(bgr)
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError(f"normals_from_vis_bgr expects HxWx3, got shape={arr.shape}")
    rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB).astype(np.float32)
    return (rgb / 255.0) * 2.0 - 1.0


def overlay_masks(
    base_bgr: np.ndarray,
    masks: Sequence[np.ndarray],
    *,
    alpha: float = 0.45,
    draw_outlines: bool = True,
) -> np.ndarray:
    """Blend each mask over ``base_bgr`` in its own color, largest painted first.

    Args:
        base_bgr: BGR uint8 image masks are drawn on top of.
        masks: Boolean or 0/255 2-D arrays, one per detected object. Painted
            largest-area-first so small masks stay visible on top of big ones.
        alpha: Blend strength for the tinted fill (0 = invisible, 1 = opaque).
        draw_outlines: When ``True``, draws a 1px white contour per mask.

    Returns:
        A new BGR uint8 image; ``base_bgr`` is not modified in place.
    """
    result = base_bgr.copy()
    height, width = result.shape[:2]

    ordered = sorted(enumerate(masks), key=lambda pair: int(np.count_nonzero(pair[1])), reverse=True)
    logger.debug("Overlaying %d masks (alpha=%.2f, outlines=%s)", len(masks), alpha, draw_outlines)

    for index, mask in ordered:
        mask_bool = mask.astype(bool) if mask.dtype != bool else mask
        if mask_bool.shape != (height, width):
            mask_bool = cv2.resize(
                mask_bool.astype(np.uint8), (width, height), interpolation=cv2.INTER_NEAREST
            ) > 0

        if not mask_bool.any():
            continue

        color = np.array(distinct_color(index), dtype=np.float32)
        region = result[mask_bool].astype(np.float32)
        blended = region * (1.0 - alpha) + color * alpha
        result[mask_bool] = blended.astype(np.uint8)

        if draw_outlines:
            contours, _ = cv2.findContours(
                mask_bool.astype(np.uint8) * 255, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            cv2.drawContours(result, contours, -1, (255, 255, 255), 1)

    return result
