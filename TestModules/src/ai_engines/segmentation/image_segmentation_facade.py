from __future__ import annotations

import logging

import numpy as np

from .image_segmentation_strategy import ImageSegmentationStrategy
from .strategies.sam_segmentation_strategy import SamSegmentationStrategy

logger = logging.getLogger(__name__)


class ImageSegmentationFacade:
    """Public entry point for point-prompted image segmentation.

    Holds exactly one :class:`ImageSegmentationStrategy`. Swapping SAM for a
    different segmentation backend is a one-line change at construction.
    """

    def __init__(self, strategy: ImageSegmentationStrategy | None = None) -> None:
        self._strategy: ImageSegmentationStrategy = strategy or SamSegmentationStrategy()
        logger.info(
            f"ImageSegmentationFacade ready (strategy={type(self._strategy).__name__})"
        )

    @property
    def strategy(self) -> ImageSegmentationStrategy:
        return self._strategy

    def get_mask_at_point(
        self,
        image: np.ndarray,
        x: int,
        y: int,
        expand_pixels: int = 0,
        use_broad_mask: bool = False,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Predict a mask at ``(x, y)`` via the active segmentation strategy.

        Returns ``(expanded_mask, original_mask)`` — see
        :meth:`ImageSegmentationStrategy.predict_mask` for the full contract.

        Method name preserved from the legacy ``SamFacadeSingleton`` to keep
        the routing strategies straightforward to migrate.
        """
        return self._strategy.predict_mask(
            image,
            x,
            y,
            expand_pixels=expand_pixels,
            use_broad_mask=use_broad_mask,
        )

    def get_all_masks_for_position(
        self,
        image: np.ndarray,
        x: int,
        y: int,
        expand_pixels: int = 0,
        use_broad_mask: bool = False,
    ) -> tuple[tuple[np.ndarray, np.ndarray], ...]:
        """Return every candidate mask the strategy produces at ``(x, y)``.

        Delegates to :meth:`ImageSegmentationStrategy.predict_all_masks`.
        Returns a tuple of ``(expanded_mask, original_mask)`` pairs — one per
        model candidate. Callers that need only the best candidate should
        prefer :meth:`get_mask_at_point`.
        """
        return self._strategy.predict_all_masks(
            image,
            x,
            y,
            expand_pixels=expand_pixels,
            use_broad_mask=use_broad_mask,
        )

    def get_all_masks_for_image(
        self,
        image: np.ndarray,
        points_per_side: int = 16,
        pred_iou_thresh: float = 0.88,
        stability_score_thresh: float = 0.95,
        min_mask_region_area: int = 0,
    ) -> tuple[np.ndarray, ...]:
        """Predict every object mask in ``image`` via the active strategy.

        Delegates to :meth:`ImageSegmentationStrategy.predict_everything`
        (prompt-free "segment everything" mode). Raises ``NotImplementedError``
        if the active strategy doesn't support it.
        """
        return self._strategy.predict_everything(
            image,
            points_per_side=points_per_side,
            pred_iou_thresh=pred_iou_thresh,
            stability_score_thresh=stability_score_thresh,
            min_mask_region_area=min_mask_region_area,
        )
