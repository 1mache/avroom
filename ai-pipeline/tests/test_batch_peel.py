from __future__ import annotations

import numpy as np

from avroom_object_removal.core.batch_peel import (
    MIN_OVERLAP_PIXELS,
    filter_masks_in_box,
    nearer_mask_index,
    peel_order,
)


def _rect_mask(h: int, w: int, y0: int, x0: int, y1: int, x1: int) -> np.ndarray:
    mask = np.zeros((h, w), dtype=np.uint8)
    mask[y0:y1, x0:x1] = 255
    return mask


def test_nearer_uses_exclusive_depth_not_overlap_surface() -> None:
    # Overlap is filled with near depth (visible front). Exclusive left is near,
    # exclusive right is far → left peels first.
    depth = np.full((20, 40), 10.0, dtype=np.float32)
    depth[:, 20:] = 50.0
    left = _rect_mask(20, 40, 0, 0, 20, 25)
    right = _rect_mask(20, 40, 0, 15, 20, 40)
    assert nearer_mask_index(left, right, depth, min_overlap=10) == 0


def test_tiny_overlap_is_independent() -> None:
    depth = np.ones((8, 8), dtype=np.float32)
    a = _rect_mask(8, 8, 0, 0, 4, 4)
    b = _rect_mask(8, 8, 3, 3, 8, 8)
    assert nearer_mask_index(a, b, depth, min_overlap=MIN_OVERLAP_PIXELS) is None


def test_peel_order_near_then_far() -> None:
    depth = np.full((20, 40), 10.0, dtype=np.float32)
    depth[:, 20:] = 50.0
    left = _rect_mask(20, 40, 0, 0, 20, 25)
    right = _rect_mask(20, 40, 0, 15, 20, 40)
    order = peel_order((right, left), depth, min_overlap=10)
    assert order[0] == 1
    assert order[1] == 0


def test_filter_masks_in_box_by_centroid() -> None:
    inside = _rect_mask(10, 10, 1, 1, 4, 4)
    outside = _rect_mask(10, 10, 7, 7, 10, 10)
    assert filter_masks_in_box((inside, outside), 0, 0, 5, 5) == [0]
