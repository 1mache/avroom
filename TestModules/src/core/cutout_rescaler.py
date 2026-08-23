from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Fraction of the raw depth ratio applied. 1.0 = full target/source; lower = milder.
_RESCALE_STRENGTH = 0.75


def depth_map_extrema(depth_map: np.ndarray) -> tuple[float, float]:
    """Return ``(deepest, closest)`` positive depths from a map.

    Production convention: higher uint8 = closer to the camera, so deepest is
    the minimum positive value and closest is the maximum.
    """
    plane = depth_map[:, :, 0] if depth_map.ndim == 3 else depth_map
    positive = plane[plane > 0]
    if positive.size == 0:
        raise ValueError("Depth map has no positive depth samples.")
    deepest = float(np.min(positive))
    closest = float(np.max(positive))
    if deepest > closest:
        deepest, closest = closest, deepest
    return deepest, closest


def _dampen_scale(raw: float) -> float:
    """Pull a raw size ratio toward 1.0 by ``_RESCALE_STRENGTH``."""
    return 1.0 + _RESCALE_STRENGTH * (raw - 1.0)


def compute_depth_scale_factor(
    source_depth: float,
    target_depth: float,
    *,
    deepest: float | None = None,
    closest: float | None = None,
) -> float:
    """Return POV scale from creation depth to placement depth.

    Convention: higher uint8 = closer to camera.
    - Deeper than start (lower target) → factor < 1 → smaller.
    - Closer to POV than start (higher target) → factor > 1 → larger.

    Raw scale is ``target / source``, then softened by ``_RESCALE_STRENGTH``.
    When ``deepest`` / ``closest`` are provided, the factor is clipped to the
    same softened scene range — no fixed global min/max.
    """
    if not math.isfinite(source_depth) or not math.isfinite(target_depth):
        raise ValueError("Depth values must be finite.")
    if source_depth <= 0 or target_depth <= 0:
        raise ValueError(
            f"Depth values must be positive (source={source_depth}, target={target_depth})."
        )
    dampened = _dampen_scale(target_depth / source_depth)
    if deepest is None or closest is None:
        return dampened
    if not math.isfinite(deepest) or not math.isfinite(closest):
        raise ValueError("Scene depth extrema must be finite.")
    if deepest <= 0 or closest <= 0:
        raise ValueError(
            f"Scene depth extrema must be positive (deepest={deepest}, closest={closest})."
        )
    # Softened sizes at the image's own back wall / nearest surface vs original.
    lo = _dampen_scale(deepest / source_depth)
    hi = _dampen_scale(closest / source_depth)
    if lo > hi:
        lo, hi = hi, lo
    return max(lo, min(hi, dampened))


def sample_depth_at_point(depth_map: np.ndarray, x: int, y: int) -> float:
    """Return uint8 depth at ``(x, y)``, clamped to the map bounds."""
    if depth_map.ndim == 3:
        depth_map = depth_map[:, :, 0]

    height, width = depth_map.shape[:2]
    clamped_x = max(0, min(x, width - 1))
    clamped_y = max(0, min(y, height - 1))
    if clamped_x != x or clamped_y != y:
        logger.debug(
            "Depth sample clamped: requested=(%d,%d) clamped=(%d,%d)",
            x,
            y,
            clamped_x,
            clamped_y,
        )
    return float(depth_map[clamped_y, clamped_x])


def scale_cutout_bgra_about_alpha_center(cutout_bgra: np.ndarray, scale_factor: float) -> np.ndarray:
    """Scale visible cutout content about its alpha-bbox center on a same-sized canvas."""
    if cutout_bgra.ndim != 3 or cutout_bgra.shape[2] < 4:
        raise ValueError("Cutout must be a BGRA image with an alpha channel.")

    height, width = cutout_bgra.shape[:2]
    alpha = cutout_bgra[:, :, 3]
    non_zero_points = cv2.findNonZero(alpha)
    if non_zero_points is None:
        raise ValueError("Cutout has no visible alpha pixels.")

    x, y, w, h = cv2.boundingRect(non_zero_points)
    left, top, right, bottom = x, y, x + w, y + h
    center_x = (left + right) / 2.0
    center_y = (top + bottom) / 2.0

    crop = cutout_bgra[top:bottom, left:right]
    new_w = max(1, int(round(crop.shape[1] * scale_factor)))
    new_h = max(1, int(round(crop.shape[0] * scale_factor)))
    scaled_crop = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    canvas = np.zeros_like(cutout_bgra)
    paste_x = int(round(center_x - new_w / 2.0))
    paste_y = int(round(center_y - new_h / 2.0))

    src_x0 = max(0, -paste_x)
    src_y0 = max(0, -paste_y)
    dst_x0 = max(0, paste_x)
    dst_y0 = max(0, paste_y)
    copy_w = min(new_w - src_x0, width - dst_x0)
    copy_h = min(new_h - src_y0, height - dst_y0)

    if copy_w <= 0 or copy_h <= 0:
        raise ValueError("Scaled cutout falls completely outside the canvas bounds.")

    canvas[dst_y0 : dst_y0 + copy_h, dst_x0 : dst_x0 + copy_w] = scaled_crop[
        src_y0 : src_y0 + copy_h,
        src_x0 : src_x0 + copy_w,
    ]
    return canvas


@dataclass(frozen=True)
class DepthRescaleResult:
    """Depth-proportional scale math without mutating cutout pixels."""

    source_average_depth: float
    target_depth: float
    scale_factor: float


@dataclass(frozen=True)
class CutoutRescaleResult:
    """Pure rescale outcome including scaled pixels (tests / debug only)."""

    cutout_bgra: np.ndarray
    source_average_depth: float
    target_depth: float
    scale_factor: float


def compute_depth_rescale(
    source_average_depth: float,
    depth_map: np.ndarray,
    x: int,
    y: int,
) -> DepthRescaleResult:
    """Compute proportional scale from depth at ``(x, y)`` without touching pixels.

    Range is scene-relative: deepest / original → smallest, closest / original →
    largest; placement uses ``target / original`` within that span.
    """
    target_depth = sample_depth_at_point(depth_map, x, y)
    deepest, closest = depth_map_extrema(depth_map)
    scale_factor = compute_depth_scale_factor(
        source_average_depth,
        target_depth,
        deepest=deepest,
        closest=closest,
    )
    return DepthRescaleResult(
        source_average_depth=source_average_depth,
        target_depth=target_depth,
        scale_factor=scale_factor,
    )


def rescale_cutout_by_depth(
    cutout_bgra: np.ndarray,
    source_average_depth: float,
    depth_map: np.ndarray,
    x: int,
    y: int,
) -> CutoutRescaleResult:
    """Rescale a BGRA cutout proportionally based on depth at ``(x, y)``.

    Production uses ``compute_depth_rescale`` only; this path mutates pixels for
    tests and optional debug tooling.
    """
    depth_result = compute_depth_rescale(source_average_depth, depth_map, x, y)
    scaled_cutout = scale_cutout_bgra_about_alpha_center(cutout_bgra, depth_result.scale_factor)
    return CutoutRescaleResult(
        cutout_bgra=scaled_cutout,
        source_average_depth=depth_result.source_average_depth,
        target_depth=depth_result.target_depth,
        scale_factor=depth_result.scale_factor,
    )
