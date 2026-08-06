from __future__ import annotations

import logging
import math

import cv2
import numpy as np

from avroom_object_removal.ai_engines.camera_calibration import CameraCalibrationResult

from ..elevation_estimation_result import ElevationEstimationResult
from ..elevation_estimation_strategy import ElevationEstimationStrategy

logger = logging.getLogger(__name__)

_DEFAULT_HFOV_DEG = 60.0
_DEFAULT_SOURCE_ELEVATION_DEG = 15.0
_ELEVATION_MIN_DEG = -10.0
_ELEVATION_MAX_DEG = 80.0
# Relative depth often inverts back-projection; map GeoCalib pitch into the
# range Zero123 tolerates without double-counting mask vertical offset.
_PITCH_HINT_MIN_DEG = 10.0
_PITCH_HINT_MAX_DEG = 22.0
_PITCH_HINT_SCALE = 0.55


class GeometricElevationEstimationStrategy(ElevationEstimationStrategy):
    """Estimate Zero123 source elevation from mask depth back-projection.

    Assumes the object is upright so gravity defines the world-up direction.
    When calibration is absent, assumes a level camera and estimates focal
    length from image width and a default horizontal field of view.
    """

    def __init__(self, *, default_hfov_deg: float = _DEFAULT_HFOV_DEG) -> None:
        self._default_hfov_deg = default_hfov_deg
        logger.info(
            "GeometricElevationEstimationStrategy configured (default_hfov_deg=%.1f)",
            default_hfov_deg,
        )

    @staticmethod
    def _default_intrinsics(width: int, height: int, hfov_deg: float) -> tuple[float, float, float, float]:
        hfov_rad = math.radians(hfov_deg)
        fx = width / (2.0 * math.tan(hfov_rad / 2.0))
        fy = fx
        cx = (width - 1) / 2.0
        cy = (height - 1) / 2.0
        return fx, fy, cx, cy

    @staticmethod
    def _world_up(calibration: CameraCalibrationResult | None) -> np.ndarray:
        if calibration is None:
            return np.array([0.0, -1.0, 0.0], dtype=np.float64)
        gravity = np.asarray(calibration.gravity, dtype=np.float64)
        norm = float(np.linalg.norm(gravity))
        if norm <= 1e-8:
            return np.array([0.0, -1.0, 0.0], dtype=np.float64)
        return -gravity / norm

    @staticmethod
    def _elevation_from_pitch_hint(calibration: CameraCalibrationResult) -> float:
        """Map GeoCalib downward pitch into a Zero123-friendly source elevation.

        GeoCalib ``pitch_deg`` is negative when the camera looks downward. Zero123
        expects a modest positive source elevation. Full physical pitch plus mask
        vertical offset overshoots (~30°+) and breaks synthesis; a scaled pitch
        hint stays in the range the model was trained on.
        """
        camera_down_deg = max(0.0, -calibration.pitch_deg)
        hinted = camera_down_deg * _PITCH_HINT_SCALE
        return max(_PITCH_HINT_MIN_DEG, min(_PITCH_HINT_MAX_DEG, hinted))

    def estimate(
        self,
        depth_map: np.ndarray,
        mask: np.ndarray,
        *,
        calibration: CameraCalibrationResult | None = None,
        image_width: int | None = None,
        image_height: int | None = None,
    ) -> ElevationEstimationResult:
        """Back-project masked depth to 3D and measure camera elevation over the object."""
        if depth_map.ndim == 3:
            depth_map = depth_map[:, :, 0]

        height, width = depth_map.shape[:2]
        if image_width is None:
            image_width = width
        if image_height is None:
            image_height = height

        mask_bool = mask > 0 if mask.dtype != bool else mask
        if mask_bool.shape[:2] != depth_map.shape[:2]:
            mask_bool = cv2.resize(
                mask_bool.astype(np.uint8),
                (width, height),
                interpolation=cv2.INTER_NEAREST,
            ).astype(bool)

        ys, xs = np.nonzero(mask_bool)
        if ys.size == 0:
            logger.warning(
                "Geometric elevation: empty mask — returning default %.0f deg",
                _DEFAULT_SOURCE_ELEVATION_DEG,
            )
            return ElevationEstimationResult(
                elevation_deg=_DEFAULT_SOURCE_ELEVATION_DEG,
                used_calibration=calibration is not None,
            )

        zs = depth_map[ys, xs].astype(np.float64)
        positive = zs > 0
        if not np.any(positive):
            logger.warning(
                "Geometric elevation: no positive depth in mask — returning default %.0f deg",
                _DEFAULT_SOURCE_ELEVATION_DEG,
            )
            return ElevationEstimationResult(
                elevation_deg=_DEFAULT_SOURCE_ELEVATION_DEG,
                used_calibration=calibration is not None,
            )

        xs = xs[positive].astype(np.float64)
        ys = ys[positive].astype(np.float64)
        zs = zs[positive]

        if calibration is not None:
            fx, fy, cx, cy = calibration.fx, calibration.fy, calibration.cx, calibration.cy
        else:
            fx, fy, cx, cy = self._default_intrinsics(image_width, image_height, self._default_hfov_deg)

        x_cam = (xs - cx) / fx * zs
        y_cam = (ys - cy) / fy * zs
        center = np.array(
            [float(np.mean(x_cam)), float(np.mean(y_cam)), float(np.mean(zs))],
            dtype=np.float64,
        )
        cam_from_object = -center
        cam_norm = float(np.linalg.norm(cam_from_object))
        if cam_norm <= 1e-8:
            logger.warning(
                "Geometric elevation: object center at camera origin — returning default %.0f deg",
                _DEFAULT_SOURCE_ELEVATION_DEG,
            )
            return ElevationEstimationResult(
                elevation_deg=_DEFAULT_SOURCE_ELEVATION_DEG,
                used_calibration=calibration is not None,
            )

        up = self._world_up(calibration)
        cos_angle = float(np.dot(cam_from_object / cam_norm, up))
        cos_angle = max(-1.0, min(1.0, cos_angle))
        raw_elevation_deg = math.degrees(math.asin(cos_angle))
        elevation_deg = max(_ELEVATION_MIN_DEG, min(_ELEVATION_MAX_DEG, raw_elevation_deg))

        if raw_elevation_deg <= 0.0:
            if calibration is not None:
                elevation_deg = self._elevation_from_pitch_hint(calibration)
                logger.info(
                    "Geometric elevation pitch hint: raw=%.2f hint=%.2f pitch=%.2f",
                    raw_elevation_deg,
                    elevation_deg,
                    calibration.pitch_deg,
                )
            else:
                elevation_deg = _DEFAULT_SOURCE_ELEVATION_DEG
                logger.info(
                    "Geometric elevation default fallback: raw=%.2f -> %.2f",
                    raw_elevation_deg,
                    elevation_deg,
                )

        logger.info(
            "Geometric elevation estimated: elevation=%.2f used_calibration=%s center_z=%.2f",
            elevation_deg,
            calibration is not None,
            center[2],
        )
        return ElevationEstimationResult(
            elevation_deg=elevation_deg,
            used_calibration=calibration is not None,
        )
