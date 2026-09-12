from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from .camera_calibration_result import CameraCalibrationResult


class CameraCalibrationStrategy(ABC):
    """Abstract strategy for estimating camera intrinsics and gravity from one image.

    Concrete implementations live under
    :mod:`avroom_object_removal.ai_engines.camera_calibration.strategies`.
    """

    @abstractmethod
    def calibrate(self, image: np.ndarray) -> CameraCalibrationResult:
        """Estimate calibration from a decoded BGR ``uint8`` image."""
        raise NotImplementedError
