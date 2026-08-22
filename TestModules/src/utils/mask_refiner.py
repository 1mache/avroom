from __future__ import annotations

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class MaskRefiner:
    """Mask post-processing helpers used across the segmentation pipeline.

    Provides three operations:

    * :meth:`expand_and_clip` - dilate then aggressively clip pixels whose
      depth differs from the click anchor by more than a tolerance. Used
      historically; kept for callers that want depth-aware refinement.
    * :meth:`expand_mask_uniform` - simple symmetric dilation with a slight
      downward bias. This is the path used by ``ObjectRemover`` today.
    * :meth:`dilate_mask` - thin wrapper around ``cv2.dilate`` for callers
      that just want N-pixel expansion (used by SAM facade).
    * :meth:`sanitize_then_expand` - click-component sanitize, then dilate.
      Use this instead of dilating a dirty SAM mask (bridging speckles).
    * :meth:`keep_click_component` - drop speckles not connected to the
      click and fill enclosed holes. Every SAM candidate goes through this.
    """

    def __init__(self, depth_tolerance: int = 10) -> None:
        self.depth_tolerance = depth_tolerance
        logger.info(f"Initialized MaskRefiner with depth tolerance {depth_tolerance}")

    def expand_and_clip(
        self,
        original_mask: np.ndarray,
        depth_map: np.ndarray,
        expand_pixels: int,
        click_x: int,
        click_y: int,
    ) -> np.ndarray:
        mask_uint8 = original_mask.astype(np.uint8)
        if mask_uint8.max() == 1:
            mask_uint8 = mask_uint8 * 255

        if expand_pixels > 0:
            kernel_size = expand_pixels * 2 + 1
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
            dilated_mask = cv2.dilate(mask_uint8, kernel, iterations=1)
        else:
            dilated_mask = mask_uint8.copy()

        if len(depth_map.shape) == 3:
            depth_map = depth_map[:, :, 0]

        # 5x5 window around the click is robust to single-pixel depth noise.
        h, w = depth_map.shape
        x_min, x_max = max(0, click_x - 2), min(w, click_x + 3)
        y_min, y_max = max(0, click_y - 2), min(h, click_y + 3)
        anchor_depth = np.median(depth_map[y_min:y_max, x_min:x_max])

        final_mask = dilated_mask.copy()

        # Drop any dilated pixel whose depth is significantly behind the click anchor.
        background_mask = (dilated_mask > 0) & (depth_map < (anchor_depth - self.depth_tolerance))
        final_mask[background_mask] = 0

        logger.info(
            f"[MaskRefiner] Anchor Depth: {anchor_depth}. "
            f"Aggressively clipped {np.sum(background_mask)} background pixels."
        )

        return final_mask

    def expand_mask_uniform(self, original_mask: np.ndarray, radius: int = 3) -> np.ndarray:
        """Dilate the mask uniformly by ~``radius`` pixels with a small downward bias.

        Depth information and click position are intentionally NOT used here -
        this is a cheap pass intended to cover 1-3 px of edge pixels SAM
        commonly misses around object boundaries.
        """
        mask_uint8 = original_mask.astype(np.uint8)
        if mask_uint8.max() == 1:
            mask_uint8 = mask_uint8 * 255

        radius = max(1, radius)
        kernel_size = radius * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        base_dilated = cv2.dilate(mask_uint8, kernel, iterations=1)

        # Extra downward reach: shadows tend to fall below objects.
        shift_pixels = 2
        shifted = np.roll(mask_uint8, shift_pixels, axis=0)
        shifted[:shift_pixels, :] = 0
        shifted_dilated = cv2.dilate(shifted, kernel, iterations=1)

        final = np.maximum(base_dilated, shifted_dilated)
        return final.astype(np.uint8)

    def keep_click_component(
        self,
        mask: np.ndarray,
        click_x: int,
        click_y: int,
    ) -> np.ndarray:
        """Reduce ``mask`` to the one blob under the click, with holes filled.

        SAM routinely returns a correct silhouette plus detached speckles
        elsewhere in the frame, and sometimes drops interior pixels. Both are
        corruption: the user clicked one object, so anything not connected to
        that click is not part of it, and an enclosed gap inside it is a miss.
        Concavities (the space between chair legs) reach the image border and
        are deliberately preserved.

        Returns the mask unchanged when the click falls outside it — callers
        rely on the click/mask agreement gate to reject that case.
        """
        mask_uint8 = mask.astype(np.uint8)
        if mask_uint8.max() == 1:
            mask_uint8 = mask_uint8 * 255

        height, width = mask_uint8.shape[:2]
        if not (0 <= click_x < width and 0 <= click_y < height):
            return mask_uint8
        if mask_uint8[click_y, click_x] == 0:
            return mask_uint8

        _, labels = cv2.connectedComponents((mask_uint8 > 0).astype(np.uint8), connectivity=8)
        click_label = int(labels[click_y, click_x])
        kept = np.where(labels == click_label, 255, 0).astype(np.uint8)

        padded = cv2.copyMakeBorder(kept, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
        outside = cv2.bitwise_not(padded)
        flood_scratch = np.zeros((padded.shape[0] + 2, padded.shape[1] + 2), np.uint8)
        cv2.floodFill(outside, flood_scratch, (0, 0), 0)
        holes = outside[1:-1, 1:-1]
        filled = cv2.bitwise_or(kept, holes)

        dropped = int(np.count_nonzero(mask_uint8 > 0)) - int(np.count_nonzero(kept))
        if dropped > 0 or np.any(holes):
            logger.debug(
                "[MaskRefiner] Sanitized mask: dropped %d detached px, filled %d hole px",
                dropped,
                int(np.count_nonzero(holes)),
            )
        return filled

    def dilate_mask(self, mask: np.ndarray, pixels: int = 0) -> np.ndarray:
        """Expand ``mask`` by ``pixels`` in all directions (no-op if pixels<=0)."""
        if pixels <= 0:
            return mask
        mask_uint8 = mask.astype(np.uint8)
        if mask_uint8.max() == 1:
            mask_uint8 = mask_uint8 * 255
        kernel_size = pixels * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        dilated = cv2.dilate(mask_uint8, kernel, iterations=1)
        return dilated.astype(np.uint8)

    def sanitize_then_expand(
        self,
        mask: np.ndarray,
        click_x: int,
        click_y: int,
        expand_pixels: int = 0,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Drop detached speckles, then dilate the click component.

        Dilating before sanitize bridges nearby SAM debris into the click blob,
        so the expanded/inpaint mask grows into floor/chair while the cutout
        (built from the sanitized original) stays tight. Always sanitize first.

        Returns:
            ``(expanded_mask, original_mask)`` where ``original_mask`` is the
            click-connected component (holes filled) and ``expanded_mask`` is
            that mask after ``expand_pixels`` dilation (a distinct copy when
            ``expand_pixels == 0``).
        """
        original_mask = self.keep_click_component(mask, click_x, click_y)
        if expand_pixels > 0:
            expanded_mask = self.dilate_mask(original_mask, pixels=expand_pixels)
        else:
            expanded_mask = original_mask.copy()
        return expanded_mask, original_mask
