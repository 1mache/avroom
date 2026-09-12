from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CameraCalibrationResult:
    """Single-image camera calibration outcome for one room photo.

    ``gravity`` is a unit vector in the camera frame pointing toward the
    physical downward direction. Intrinsics follow OpenCV pinhole convention
    (``fx``, ``fy``, ``cx``, ``cy`` in pixels).
    """

    gravity: tuple[float, float, float]
    roll_deg: float
    pitch_deg: float
    fx: float
    fy: float
    cx: float
    cy: float
    confidence: float | None = None
    camera_model: str = "pinhole"
