from __future__ import annotations

import math
import sys
from unittest.mock import MagicMock

import numpy as np

sys.modules.setdefault("torch", MagicMock())

from avroom_object_removal.ai_engines.camera_calibration import CameraCalibrationResult
from avroom_object_removal.ai_engines.elevation_estimation import (
    ElevationEstimationFacade,
    GeometricElevationEstimationStrategy,
)


def test_geometric_elevation_uses_level_camera_when_no_calibration() -> None:
    """A mask centered low in the frame should yield positive elevation."""
    height, width = 480, 640
    depth_map = np.full((height, width), 128, dtype=np.uint8)
    mask = np.zeros((height, width), dtype=np.uint8)
    mask[320:400, 280:360] = 255

    result = ElevationEstimationFacade(
        strategy=GeometricElevationEstimationStrategy(default_hfov_deg=60.0)
    ).estimate(depth_map, mask)

    assert result.used_calibration is False
    assert 5.0 <= result.elevation_deg <= 45.0


def test_geometric_elevation_respects_gravity_from_calibration() -> None:
    """When gravity indicates a pitched camera, world-up should change the estimate."""
    height, width = 480, 640
    depth_map = np.full((height, width), 100, dtype=np.uint8)
    mask = np.zeros((height, width), dtype=np.uint8)
    mask[200:280, 280:360] = 255

    calib = CameraCalibrationResult(
        gravity=(0.0, 1.0, 0.0),
        roll_deg=0.0,
        pitch_deg=20.0,
        fx=500.0,
        fy=500.0,
        cx=width / 2.0,
        cy=height / 2.0,
    )

    facade = ElevationEstimationFacade(strategy=GeometricElevationEstimationStrategy())
    without = facade.estimate(depth_map, mask, calibration=None)
    with_calib = facade.estimate(depth_map, mask, calibration=calib)

    assert without.used_calibration is False
    assert with_calib.used_calibration is True
    assert math.isfinite(with_calib.elevation_deg)


def test_geometric_elevation_uses_pitch_hint_for_downward_floor_photo() -> None:
    """Unreliable depth geometry should yield a modest pitch hint, not ~32 deg."""
    height, width = 1200, 1600
    depth_map = np.full((height, width), 190, dtype=np.uint8)
    mask = np.zeros((height, width), dtype=np.uint8)
    mask[900:1050, 650:850] = 255

    calib = CameraCalibrationResult(
        gravity=(0.0, 0.42, 0.91),
        roll_deg=0.78,
        pitch_deg=-25.45,
        fx=1065.1,
        fy=1065.1,
        cx=799.5,
        cy=599.5,
    )

    result = ElevationEstimationFacade(
        strategy=GeometricElevationEstimationStrategy()
    ).estimate(depth_map, mask, calibration=calib)

    assert result.used_calibration is True
    assert 10.0 <= result.elevation_deg <= 22.0
    assert result.elevation_deg < 25.0
