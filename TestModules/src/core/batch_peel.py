from __future__ import annotations

import numpy as np

from ..utils.mask_bool import mask_to_bool as mask_bool

# Overlaps smaller than this are treated as independent (not a peel stack).
MIN_OVERLAP_PIXELS: int = 200


def overlap_pixel_count(a: np.ndarray, b: np.ndarray) -> int:
    """Count pixels that are foreground in both masks."""
    return int(np.count_nonzero(mask_bool(a) & mask_bool(b)))


def _median_depth(depth: np.ndarray, region: np.ndarray) -> float:
    if not region.any():
        return float("nan")
    return float(np.median(depth[region]))


def nearer_mask_index(
    mask_a: np.ndarray,
    mask_b: np.ndarray,
    depth: np.ndarray,
    min_overlap: int = MIN_OVERLAP_PIXELS,
) -> int | None:
    """Return 0 if A peels first, 1 if B peels first, or None if independent.

    Overlap decides they are a stack. A single depth map has one value per
    overlap pixel (the visible surface), so order uses median depth on each
    mask's exclusive pixels. Lower depth = closer to camera = first.
    """
    a = mask_bool(mask_a)
    b = mask_bool(mask_b)
    overlap = a & b
    if int(np.count_nonzero(overlap)) < min_overlap:
        return None
    d_a = _median_depth(depth, a & ~b)
    d_b = _median_depth(depth, b & ~a)
    if np.isnan(d_a) and np.isnan(d_b):
        d_a = _median_depth(depth, a)
        d_b = _median_depth(depth, b)
    if np.isnan(d_a) or np.isnan(d_b):
        return 0
    if d_a <= d_b:
        return 0
    return 1


def peel_order(
    masks: tuple[np.ndarray, ...] | list[np.ndarray],
    depth: np.ndarray,
    min_overlap: int = MIN_OVERLAP_PIXELS,
) -> list[int]:
    """Return mask indices in peel order (closer stacks first).

    Independent masks keep relative input order. Cyclic depth order falls
    back to input index.
    """
    n = len(masks)
    predecessors: dict[int, set[int]] = {i: set() for i in range(n)}
    for i in range(n):
        for j in range(i + 1, n):
            nearer = nearer_mask_index(masks[i], masks[j], depth, min_overlap=min_overlap)
            if nearer is None:
                continue
            if nearer == 0:
                predecessors[j].add(i)
            else:
                predecessors[i].add(j)

    remaining = set(range(n))
    ordered: list[int] = []
    while remaining:
        ready = [i for i in sorted(remaining) if predecessors[i].isdisjoint(remaining)]
        if not ready:
            ordered.extend(sorted(remaining))
            break
        pick = ready[0]
        ordered.append(pick)
        remaining.remove(pick)
    return ordered


def centroid_in_box(
    mask: np.ndarray,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
) -> bool:
    """True when the mask foreground centroid lies inside the inclusive box."""
    region = mask_bool(mask)
    if not region.any():
        return False
    ys, xs = np.nonzero(region)
    cx = float(xs.mean())
    cy = float(ys.mean())
    left, right = (min(x0, x1), max(x0, x1))
    top, bottom = (min(y0, y1), max(y0, y1))
    return left <= cx <= right and top <= cy <= bottom


def filter_masks_in_box(
    masks: tuple[np.ndarray, ...] | list[np.ndarray],
    x0: int,
    y0: int,
    x1: int,
    y1: int,
) -> list[int]:
    """Return indices of masks whose centroid falls inside the box."""
    return [i for i, mask in enumerate(masks) if centroid_in_box(mask, x0, y0, x1, y1)]
