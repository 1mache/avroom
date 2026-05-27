from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class ImageSegmentationStrategy(ABC):
    """Abstract Strategy for point-based image segmentation.

    Given an image (in whatever representation the strategy expects - some
    consume RGB, some consume an adapted depth map) and a single foreground
    point, return a binary mask covering the object touched by the point.
    """

    @abstractmethod
    def predict_mask(
        self,
        image: np.ndarray,
        x: int,
        y: int,
        *,
        expand_pixels: int = 0,
        use_broad_mask: bool = False,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Predict an object mask containing pixel ``(x, y)``.

        Args:
            image: Input image array. The exact channel layout is strategy-
                specific; for SAM this is the 3-channel adapted depth map
                produced by :class:`SamImageAdapter`.
            x: Foreground point X coordinate (image pixel space).
            y: Foreground point Y coordinate (image pixel space).
            expand_pixels: Optional uniform dilation (px) applied after the
                model's raw prediction. ``0`` disables expansion.
            use_broad_mask: When ``True`` the strategy may return a more
                generous mask candidate (e.g., SAM's "broad" output index).

        Returns:
            A ``(expanded_mask, original_mask)`` tuple of 2-D ``uint8`` masks
            (0 / 255) sized to match ``image``. ``original_mask`` is the raw
            model output; ``expanded_mask`` is ``original_mask`` after any
            ``expand_pixels`` dilation. When ``expand_pixels == 0`` the two
            arrays are distinct (non-aliased) copies.
        """
        raise NotImplementedError

    @abstractmethod
    def predict_all_masks(
        self,
        image: np.ndarray,
        x: int,
        y: int,
        *,
        expand_pixels: int = 0,
        use_broad_mask: bool = False,
    ) -> tuple[tuple[np.ndarray, np.ndarray], ...]:
        """Predict masks for every candidate the model produces at ``(x, y)``.

        Where ``predict_mask`` selects a single best candidate, this method
        returns every candidate the underlying model generates so callers can
        evaluate all options (e.g. all three SAM multimask outputs).

        Args:
            image: Input image array — same contract as :meth:`predict_mask`.
            x: Foreground point X coordinate (image pixel space).
            y: Foreground point Y coordinate (image pixel space).
            expand_pixels: Optional uniform dilation applied to each candidate
                after the model's raw prediction. ``0`` disables expansion.
            use_broad_mask: Forwarded to the strategy for interface symmetry;
                individual strategies may or may not act on it.

        Returns:
            A tuple of ``(expanded_mask, original_mask)`` pairs — one per
            model candidate. Each mask is a 2-D ``uint8`` array (0 / 255)
            sized to match ``image``. Within each pair ``original_mask`` is
            the raw candidate; ``expanded_mask`` is that candidate after any
            ``expand_pixels`` dilation (a distinct copy when ``expand_pixels
            == 0``).
        """
        raise NotImplementedError
