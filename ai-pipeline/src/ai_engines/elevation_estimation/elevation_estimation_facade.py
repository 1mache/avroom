from __future__ import annotations

import logging

import numpy as np

from avroom_object_removal.ai_engines.camera_calibration import CameraCalibrationResult

from .elevation_estimation_result import ElevationEstimationResult
from .elevation_estimation_strategy import ElevationEstimationStrategy
from .strategies.geometric_elevation_estimation_strategy import GeometricElevationEstimationStrategy

logger = logging.getLogger(__name__)


class ElevationEstimationFacade:
    """Public entry point for object-centric source elevation estimation."""

    def __init__(self, strategy: ElevationEstimationStrategy | None = None) -> None:
        self._strategy: ElevationEstimationStrategy = (
            strategy or GeometricElevationEstimationStrategy()
        )
        logger.info(
            "ElevationEstimationFacade ready (strategy=%s)",
            type(self._strategy).__name__,
        )

    @property
    def strategy(self) -> ElevationEstimationStrategy:
        return self._strategy

    def estimate(
        self,
        depth_map: np.ndarray,
        mask: np.ndarray,
        *,
        calibration: CameraCalibrationResult | None = None,
        image_width: int | None = None,
        image_height: int | None = None,
    ) -> ElevationEstimationResult:
        """Estimate source elevation for one object mask."""
        return self._strategy.estimate(
            depth_map,
            mask,
            calibration=calibration,
            image_width=image_width,
            image_height=image_height,
        )
