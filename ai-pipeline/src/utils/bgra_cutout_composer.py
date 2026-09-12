from __future__ import annotations

import cv2
import numpy as np


class BgraCutoutComposer:
    """Build a BGRA cutout image from an original BGR image and a binary mask.

    Output is OpenCV BGRA with:

    - alpha = 255 inside the mask
    - alpha = 0   outside the mask (RGB channels are zeroed too, so callers
      that ignore alpha still see a clean transparent background)
    """

    @staticmethod
    def compose_original_overlap_bgra(original_bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
        if original_bgr is None or not isinstance(original_bgr, np.ndarray):
            raise ValueError("original_bgr must be a numpy ndarray")
        if mask is None or not isinstance(mask, np.ndarray):
            raise ValueError("mask must be a numpy ndarray")

        if mask.shape[:2] != original_bgr.shape[:2]:
            mask = cv2.resize(
                mask,
                (original_bgr.shape[1], original_bgr.shape[0]),
                interpolation=cv2.INTER_NEAREST,
            )

        if mask.dtype == bool:
            mask_bool = mask
        else:
            mask_max = float(np.max(mask)) if mask.size else 0.0
            if mask_max <= 1.0:
                mask_bool = mask > 0.5
            else:
                mask_bool = mask > 127

        alpha = mask_bool.astype(np.uint8) * 255

        bgra = cv2.cvtColor(original_bgr, cv2.COLOR_BGR2BGRA)
        bgra[..., 3] = alpha
        bgra[..., :3] = bgra[..., :3] * mask_bool.astype(np.uint8)[..., None]

        return bgra
