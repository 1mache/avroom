from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from avroom_object_removal.ai_engines.camera_calibration import CameraCalibrationResult

from .elevation_estimation_result import ElevationEstimationResult


class ElevationEstimationStrategy(ABC):
    """Abstract strategy for estimating object-centric source elevation."""

    @abstractmethod
    def estimate(
        self,
        depth_map: np.ndarray,
        mask: np.ndarray,
        *,
        calibration: CameraCalibrationResult | None = None,
        image_width: int | None = None,
        image_height: int | None = None,
    ) -> ElevationEstimationResult:
        """Estimate source elevation from depth, mask, and optional calibration."""
        raise NotImplementedError
