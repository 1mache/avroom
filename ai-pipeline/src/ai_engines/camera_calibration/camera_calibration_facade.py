from __future__ import annotations

import logging

import numpy as np

from .camera_calibration_result import CameraCalibrationResult
from .camera_calibration_strategy import CameraCalibrationStrategy
from .strategies.geocalib_camera_calibration_strategy import GeoCalibCameraCalibrationStrategy

logger = logging.getLogger(__name__)


class CameraCalibrationFacade:
    """Public entry point for single-image camera calibration.

    Holds exactly one :class:`CameraCalibrationStrategy`. The default backend
    is :class:`GeoCalibCameraCalibrationStrategy`.
    """

    def __init__(self, strategy: CameraCalibrationStrategy | None = None) -> None:
        self._strategy: CameraCalibrationStrategy = (
            strategy or GeoCalibCameraCalibrationStrategy()
        )
        logger.info(
            "CameraCalibrationFacade ready (strategy=%s)",
            type(self._strategy).__name__,
        )

    @property
    def strategy(self) -> CameraCalibrationStrategy:
        return self._strategy

    def calibrate(self, image: np.ndarray) -> CameraCalibrationResult:
        """Estimate gravity and intrinsics from a decoded BGR ``uint8`` image."""
        return self._strategy.calibrate(image)
