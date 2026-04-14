import cv2
import numpy as np


class MaskOverlapRGBAComposer:
    """
    Composes a transparent view of an original image using a mask.

    Output is BGRA (OpenCV order) where:
    - alpha=255 where mask overlaps
    - alpha=0 everywhere else (pixels are fully transparent)
    """

    @staticmethod
    def compose_original_overlap_bgra(original_bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
        if original_bgr is None or not isinstance(original_bgr, np.ndarray):
            raise ValueError("original_bgr must be a numpy ndarray")
        if mask is None or not isinstance(mask, np.ndarray):
            raise ValueError("mask must be a numpy ndarray")

        if mask.shape[:2] != original_bgr.shape[:2]:
            # SAM/depth/mask sometimes produce slightly different sizes.
            mask = cv2.resize(mask, (original_bgr.shape[1], original_bgr.shape[0]), interpolation=cv2.INTER_NEAREST)

        if mask.dtype == bool:
            mask_bool = mask
        else:
            mask_max = float(np.max(mask)) if mask.size else 0.0
            if mask_max <= 1.0:
                mask_bool = mask > 0.5
            else:
                mask_bool = mask > 127

        alpha = mask_bool.astype(np.uint8) * 255

        # Convert to BGRA then apply alpha and (optionally) zero out transparent RGB.
        bgra = cv2.cvtColor(original_bgr, cv2.COLOR_BGR2BGRA)
        bgra[..., 3] = alpha
        bgra[..., :3] = bgra[..., :3] * mask_bool.astype(np.uint8)[..., None]

        return bgra

