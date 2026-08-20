from __future__ import annotations

from typing import Sequence

import cv2
import numpy as np


def alpha_from_cutout(cutout_bgra: np.ndarray) -> np.ndarray:
    """Return a boolean alpha mask from a BGRA cutout."""
    if cutout_bgra.ndim != 3 or cutout_bgra.shape[2] < 4:
        return np.zeros(cutout_bgra.shape[:2], dtype=bool)
    return cutout_bgra[:, :, 3] > 0


def mask_alpha_iou(a: np.ndarray, b: np.ndarray) -> float:
    """IoU between two boolean alpha masks."""
    if a.shape != b.shape:
        raise ValueError("IoU expects masks with the same shape")
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    if union == 0:
        return 0.0
    return float(inter) / float(union)


def largest_iou_cluster(
    *,
    indices: Sequence[int],
    cutouts_bgra: Sequence[np.ndarray],
    threshold: float = 0.55,
) -> tuple[int, ...]:
    """Return the largest connected component by alpha IoU threshold.

    If no edges exist between any pair (all isolated), returns ``indices``.
    """
    n = len(indices)
    if n == 0:
        return ()

    masks = {i: alpha_from_cutout(cutouts_bgra[i]) for i in indices}

    # Build adjacency graph where an edge means IoU >= threshold.
    adj: dict[int, set[int]] = {i: set() for i in indices}
    for a_i in range(n):
        for b_i in range(a_i + 1, n):
            ia = indices[a_i]
            ib = indices[b_i]
            iou = mask_alpha_iou(masks[ia], masks[ib])
            if iou >= threshold:
                adj[ia].add(ib)
                adj[ib].add(ia)

    seen: set[int] = set()
    components: list[list[int]] = []
    for start in indices:
        if start in seen:
            continue
        stack = [start]
        comp: list[int] = []
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            comp.append(cur)
            stack.extend(sorted(adj[cur]))
        components.append(comp)

    if max(len(c) for c in components) <= 1:
        return tuple(indices)

    # Deterministic tie-break: largest size, then smallest index.
    best = max(components, key=lambda c: (len(c), -min(c)))
    return tuple(sorted(best))


def _mask_to_uint8(mask_bool: np.ndarray) -> np.ndarray:
    return (mask_bool.astype(np.uint8) * 255).copy()


def boundary_edge_score(scene_bgr: np.ndarray | None, mask_bool: np.ndarray) -> float:
    """Fraction of mask boundary pixels that land on image edges."""
    if scene_bgr is None or mask_bool.sum() == 0:
        return 0.0

    gray = cv2.cvtColor(scene_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 180)  # returns 0/255

    mask_uint8 = _mask_to_uint8(mask_bool)
    kernel = np.ones((3, 3), np.uint8)
    dilated = cv2.dilate(mask_uint8, kernel, iterations=1)
    eroded = cv2.erode(mask_uint8, kernel, iterations=1)
    boundary = (dilated > 0) & (eroded == 0)

    boundary_count = int(boundary.sum())
    if boundary_count == 0:
        return 0.0

    edge_hits = int(np.logical_and(boundary, edges > 0).sum())
    return float(edge_hits) / float(boundary_count)


def depth_coherence_score(
    depth_map: np.ndarray | None,
    mask_bool: np.ndarray,
    click_xy: tuple[int, int],
    *,
    tol: float = 0.15,
) -> float:
    """How consistent mask depths are with the click depth."""
    if depth_map is None or mask_bool.sum() == 0:
        return 0.0

    depth = depth_map
    if depth.ndim == 3:
        depth = depth[:, :, 0]
    if depth.ndim != 2:
        return 0.0

    h, w = depth.shape[:2]
    x, y = click_xy
    if x < 0 or y < 0 or x >= w or y >= h:
        return 0.0

    depth_norm = depth.astype(np.float32) / 255.0
    click_depth = float(depth_norm[y, x])

    mask_depths = depth_norm[mask_bool]
    if mask_depths.size == 0:
        return 0.0

    mismatched = np.abs(mask_depths - click_depth) > tol
    mismatch_fraction = float(mismatched.sum()) / float(mask_depths.size)
    return 1.0 - mismatch_fraction


def purity_score(
    *,
    scene_bgr: np.ndarray | None,
    depth_map: np.ndarray | None,
    mask_bool: np.ndarray,
    click_xy: tuple[int, int],
) -> float:
    """Composite purity score: boundary alignment + depth coherence."""
    b = boundary_edge_score(scene_bgr, mask_bool)
    if depth_map is None:
        return b

    d = depth_coherence_score(depth_map, mask_bool, click_xy)
    return 0.5 * b + 0.5 * d


def mask_area_fraction(mask_bool: np.ndarray) -> float:
    """Fraction of the frame covered by ``mask_bool``."""
    if mask_bool.size == 0:
        return 0.0
    return float(np.count_nonzero(mask_bool)) / float(mask_bool.size)


def area_biased_purity_score(
    *,
    purity: float,
    area_fraction: float,
    max_area_fraction: float,
    area_exponent: float = 0.75,
) -> float:
    """Blend purity with relative mask area inside a consensus cluster.

    Thin-leg furniture often scores higher on boundary purity when legs are
    dropped; boosting area among siblings favors complete silhouettes.
    """
    if max_area_fraction <= 0.0:
        return purity
    relative_area = area_fraction / max_area_fraction
    return purity * (relative_area**area_exponent)

