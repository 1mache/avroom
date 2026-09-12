from __future__ import annotations

import sys
from unittest.mock import MagicMock

import numpy as np
import pytest

sys.modules.setdefault("torch", MagicMock())

from avroom_object_removal.ai_engines.camera_calibration import (
    CameraCalibrationFacade,
    CameraCalibrationResult,
    CameraCalibrationStrategy,
)


class _StubCalibrationStrategy(CameraCalibrationStrategy):
    def __init__(self, result: CameraCalibrationResult) -> None:
        self._result = result
        self.call_count = 0

    def calibrate(self, image: np.ndarray) -> CameraCalibrationResult:
        self.call_count += 1
        return self._result


def test_camera_calibration_facade_delegates_to_strategy() -> None:
    expected = CameraCalibrationResult(
        gravity=(0.0, 1.0, 0.0),
        roll_deg=0.0,
        pitch_deg=5.0,
        fx=500.0,
        fy=500.0,
        cx=320.0,
        cy=240.0,
        confidence=0.9,
    )
    stub = _StubCalibrationStrategy(expected)
    facade = CameraCalibrationFacade(strategy=stub)
    image = np.zeros((480, 640, 3), dtype=np.uint8)

    result = facade.calibrate(image)

    assert result == expected
    assert stub.call_count == 1


def test_camera_calibration_facade_rejects_non_bgr_input_via_strategy() -> None:
    class _RaisingStrategy(CameraCalibrationStrategy):
        def calibrate(self, image: np.ndarray) -> CameraCalibrationResult:
            if image.ndim != 3:
                raise ValueError("bad shape")
            raise AssertionError("should not reach")

    facade = CameraCalibrationFacade(strategy=_RaisingStrategy())
    with pytest.raises(ValueError, match="bad shape"):
        facade.calibrate(np.zeros((8, 8), dtype=np.uint8))
