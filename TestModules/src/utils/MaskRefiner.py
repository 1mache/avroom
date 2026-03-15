import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)

class MaskRefiner:
    """
    Intelligently refines and dilates masks using Aggressive Depth-Guided Clipping.
    Prevents mask bleeding by comparing EVERY pixel to the depth of the user's click.
    """
    def __init__(self, depth_tolerance: int = 10):
        # The allowed depth difference (0-255 scale) before a pixel is considered 'background'
        self.depth_tolerance = depth_tolerance
        logger.info(f"Initialized MaskRefiner with depth tolerance {depth_tolerance}")

    def expand_and_clip(self, original_mask: np.ndarray, depth_map: np.ndarray, expand_pixels: int, click_x: int, click_y: int) -> np.ndarray:
        # 1. Normalize mask to uint8
        mask_uint8 = original_mask.astype(np.uint8)
        if mask_uint8.max() == 1:
            mask_uint8 = mask_uint8 * 255

        # 2. Blind Dilation (Expand everywhere)
        if expand_pixels > 0:
            kernel_size = expand_pixels * 2 + 1
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
            dilated_mask = cv2.dilate(mask_uint8, kernel, iterations=1)
        else:
            dilated_mask = mask_uint8.copy()

        # 3. Depth Normalization
        if len(depth_map.shape) == 3:
            depth_map = depth_map[:, :, 0]

        # 4. Get Anchor Depth (The exact depth of the user's click)
        # We use a 5x5 window around the click to be immune to single-pixel noise
        h, w = depth_map.shape
        x_min, x_max = max(0, click_x - 2), min(w, click_x + 3)
        y_min, y_max = max(0, click_y - 2), min(h, click_y + 3)
        anchor_depth = np.median(depth_map[y_min:y_max, x_min:x_max])

        final_mask = dilated_mask.copy()

        # 5. AGGRESSIVE DEPTH CLIPPING (The Fix!)
        # We scan the ENTIRE mask. We don't trust SAM anymore.
        # In MiDaS depth maps: lower value = further away.
        # If ANY pixel is significantly further away than the anchor, it gets deleted!
        background_mask = (dilated_mask > 0) & (depth_map < (anchor_depth - self.depth_tolerance))

        # Zero out the background pixels
        final_mask[background_mask] = 0

        logger.info(f"[MaskRefiner] Anchor Depth: {anchor_depth}. Aggressively clipped {np.sum(background_mask)} background pixels.")

        return final_mask

    def expand_mask_uniform(self, original_mask: np.ndarray, radius: int = 3) -> np.ndarray:
        """
        Enlarge a binary mask by ~3 pixels in all directions,
        and ~5 pixels downward (towards increasing Y).
        Depth information and click position are NOT used here.
        """
        mask_uint8 = original_mask.astype(np.uint8)
        if mask_uint8.max() == 1:
            mask_uint8 = mask_uint8 * 255

        # Base symmetric dilation (≈3px all around)
        radius = max(1, radius)
        kernel_size = radius * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        base_dilated = cv2.dilate(mask_uint8, kernel, iterations=1)

        # Extra downward bias: shift mask down by 2 pixels, then dilate and merge
        shift_pixels = 2  # extra reach downward (3 + 2 ≈ 5)
        shifted = np.roll(mask_uint8, shift_pixels, axis=0)
        # Zero out the wrapped top rows created by np.roll
        shifted[:shift_pixels, :] = 0
        shifted_dilated = cv2.dilate(shifted, kernel, iterations=1)

        final = np.maximum(base_dilated, shifted_dilated)
        return final.astype(np.uint8)

    def dilate_mask(self, mask: np.ndarray, pixels: int = 0) -> np.ndarray:
        """Expand mask by `pixels` in all directions (used by SAM facade when expand_pixels > 0)."""
        if pixels <= 0:
            return mask
        mask_uint8 = mask.astype(np.uint8)
        if mask_uint8.max() == 1:
            mask_uint8 = mask_uint8 * 255
        kernel_size = pixels * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        dilated = cv2.dilate(mask_uint8, kernel, iterations=1)
        return dilated.astype(np.uint8)