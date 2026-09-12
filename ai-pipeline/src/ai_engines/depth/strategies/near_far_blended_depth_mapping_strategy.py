from __future__ import annotations

import logging

import cv2
import numpy as np

from ..depth_mapping_strategy import DepthMappingStrategy
from .depth_anything_mapping_strategy import DepthAnythingMappingStrategy

logger = logging.getLogger(__name__)


class NearFarBlendedDepthMappingStrategy(DepthMappingStrategy):
    """Compose two depth strategies (one near-field, one far-field) via alpha
    blending.

    The near map's normalized confidence (its own depth value scaled to 0..1)
    is used as the alpha weight on top of the far map. This avoids the hard
    seams that simple averaging produces between near-field and far-field
    behavior - the dominant model "wins" in regions where its values are
    strong.

    Defaults reproduce the legacy ``OptimizedDepthFacade`` behavior:

    * Near = Depth Anything V2 Small
    * Far  = LiheYoung Depth Anything Small
    """

    DEFAULT_NEAR_MODEL: str = "depth-anything/Depth-Anything-V2-Small-hf"
    DEFAULT_FAR_MODEL: str = "LiheYoung/depth-anything-small-hf"

    def __init__(
        self,
        near_strategy: DepthMappingStrategy | None = None,
        far_strategy: DepthMappingStrategy | None = None,
    ) -> None:
        self._near = near_strategy or DepthAnythingMappingStrategy(
            model_name=self.DEFAULT_NEAR_MODEL
        )
        self._far = far_strategy or DepthAnythingMappingStrategy(
            model_name=self.DEFAULT_FAR_MODEL
        )
        logger.info(
            "NearFarBlendedDepthMappingStrategy created "
            f"(near={type(self._near).__name__}, far={type(self._far).__name__})"
        )

    def map_depth(self, image: np.ndarray) -> np.ndarray:
        depth_near = self._near.map_depth(image)
        if depth_near.ndim == 3:
            depth_near = cv2.cvtColor(depth_near, cv2.COLOR_RGB2GRAY)

        depth_far = self._far.map_depth(image)
        if depth_far.ndim == 3:
            depth_far = cv2.cvtColor(depth_far, cv2.COLOR_RGB2GRAY)

        depth_near_norm = cv2.normalize(depth_near, None, 0, 255, cv2.NORM_MINMAX).astype(np.float32)
        depth_far_norm = cv2.normalize(depth_far, None, 0, 255, cv2.NORM_MINMAX).astype(np.float32)

        # Near-field map's own normalized depth is the alpha: closer pixels
        # rely on the near model, farther pixels fall back to the far model.
        alpha = depth_near_norm / 255.0
        blended = (depth_near_norm * alpha) + (depth_far_norm * (1.0 - alpha))

        return blended.astype(np.uint8)
