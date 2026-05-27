from __future__ import annotations

import cv2
import numpy as np


def ensure_mask_hw(mask: np.ndarray, target_hw: tuple[int, int]) -> np.ndarray:
    """Resize ``mask`` to ``target_hw`` and normalise to binary ``uint8`` semantics.

    Resizes with nearest-neighbor interpolation so mask boundaries are not
    blurred, then converts float or boolean masks to ``uint8`` (0 / 255) so
    all downstream consumers can apply a consistent ``> 127`` threshold.

    Args:
        mask: Input mask — may be 2-D or 3-D (single channel), boolean,
            float in [0, 1], or ``uint8`` in [0, 255].
        target_hw: ``(height, width)`` the output mask must match.

    Returns:
        A 2-D ``uint8`` or boolean ``ndarray`` of shape ``target_hw`` that
        preserves the binary foreground/background semantics of the input.
    """
    h, w = target_hw

    if mask.ndim == 3:
        mask = mask[:, :, 0]

    if mask.shape[:2] != (h, w):
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)

    if mask.dtype == bool:
        return mask

    thresh = 0.5 if float(mask.max()) <= 1.0 else 127
    return (mask > thresh).astype(np.uint8) * 255
