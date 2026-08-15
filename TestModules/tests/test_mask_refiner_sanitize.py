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
