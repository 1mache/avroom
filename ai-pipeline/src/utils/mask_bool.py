from __future__ import annotations

import numpy as np


def mask_to_bool(mask: np.ndarray) -> np.ndarray:
    """Interpret a mask of ambiguous scale/dtype as a 2-D boolean foreground array.

    Masks flow through this pipeline as 0/1 float, 0/255 ``uint8``, or
    boolean, sometimes with a redundant trailing channel dim. This is the
    single place that resolves that ambiguity: boolean input passes through
    unchanged; ``uint8`` (or anything else with values above 1) is treated
    as 0-255 and thresholded at 127; everything else is treated as 0-1 and
    thresholded at 0.5.
    """
    if mask.ndim == 3:
        mask = mask[:, :, 0]
    if mask.dtype == bool:
        return mask
    if mask.dtype == np.uint8 or (mask.size and float(mask.max()) > 1.0):
        return mask > 127
    return mask > 0.5


def mask_pixel_count(mask: np.ndarray) -> int:
    """Foreground pixel count for a mask of ambiguous scale/dtype."""
    return int(np.count_nonzero(mask_to_bool(mask)))
