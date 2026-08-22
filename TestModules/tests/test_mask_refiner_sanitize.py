from __future__ import annotations

import numpy as np

from avroom_object_removal.utils.mask_refiner import MaskRefiner

_REFINER = MaskRefiner()


def _blank() -> np.ndarray:
    return np.zeros((100, 100), dtype=np.uint8)


def test_detached_speckles_are_dropped() -> None:
    mask = _blank()
    mask[20:60, 20:60] = 255
    mask[5:8, 90:94] = 255
    mask[80:83, 10:14] = 255

    sanitized = _REFINER.keep_click_component(mask, 40, 40)

    assert sanitized[40, 40] == 255
    assert sanitized[6, 91] == 0
    assert sanitized[81, 12] == 0
    assert int(np.count_nonzero(sanitized)) == 40 * 40


def test_enclosed_hole_is_filled() -> None:
    mask = _blank()
    mask[20:60, 20:60] = 255
    mask[35:45, 35:45] = 0

    sanitized = _REFINER.keep_click_component(mask, 25, 25)

    assert sanitized[40, 40] == 255
    assert int(np.count_nonzero(sanitized)) == 40 * 40


def test_gap_reaching_the_border_is_preserved() -> None:
    """The space between chair legs must survive: it is concavity, not a hole."""
    mask = _blank()
    mask[20:40, 20:60] = 255
    mask[40:100, 20:26] = 255
    mask[40:100, 54:60] = 255

    sanitized = _REFINER.keep_click_component(mask, 40, 30)

    assert sanitized[70, 40] == 0
    assert sanitized[70, 22] == 255
    assert sanitized[70, 56] == 255


def test_click_outside_mask_leaves_it_untouched() -> None:
    mask = _blank()
    mask[20:60, 20:60] = 255

    sanitized = _REFINER.keep_click_component(mask, 5, 5)

    assert np.array_equal(sanitized, mask)


def test_sanitize_then_expand_does_not_bridge_detached_speckles() -> None:
    """Dilate-before-sanitize used to merge nearby speckles into the inpaint mask."""
    mask = _blank()
    mask[30:70, 30:70] = 255
    # Gap of 8 px; expand=10 bridges if dilation runs on the dirty raw mask.
    mask[48:52, 78:82] = 255

    expanded, original = _REFINER.sanitize_then_expand(mask, 50, 50, expand_pixels=10)

    assert original[50, 80] == 0
    assert expanded[50, 80] == 0
    assert int(np.count_nonzero(original)) == 40 * 40
    # Uniform 10 px dilate grows the square to x≈79; the speckle at x=80 stays out.
    assert expanded[50, 50] == 255
    assert expanded[50, 79] == 255
    assert mask[50, 80] == 255  # raw still has the speckle
    # Regression: dilate-then-sanitize would have kept x=80 after bridging.
