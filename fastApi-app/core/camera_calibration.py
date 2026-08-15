from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

import cv2
import numpy as np

from core.avroom_package import load_avroom_attr
from core.depth_cache import memory_image_key

logger = logging.getLogger(__name__)

_CALIBRATION_MODULE = "avroom_object_removal.ai_engines.camera_calibration"


@dataclass(frozen=True)
class CameraCalibrationOutcome:
    """Picklable camera calibration result for inference jobs."""

    gravity: tuple[float, float, float]
    roll_deg: float
    pitch_deg: float
    fx: float
    fy: float
    cx: float
    cy: float
    confidence: float | None
    camera_model: str

    def to_cache_dict(self) -> dict[str, Any]:
        """Serialize to JSON-friendly mapping for session disk cache."""
        return asdict(self)


def calibrate_upload_image(image_bytes: bytes) -> CameraCalibrationOutcome:
    """Run camera calibration on raw upload bytes."""
    decoded = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if decoded is None:
        raise ValueError("Upload bytes are not a valid image.")

    facade = load_avroom_attr("CameraCalibrationFacade", _CALIBRATION_MODULE)()
    image_key = memory_image_key(image_bytes)
    logger.info("Camera calibration start: key=%s shape=%s", image_key[:24], decoded.shape)
    result = facade.calibrate(decoded)
    outcome = CameraCalibrationOutcome(
        gravity=result.gravity,
        roll_deg=result.roll_deg,
        pitch_deg=result.pitch_deg,
        fx=result.fx,
        fy=result.fy,
        cx=result.cx,
        cy=result.cy,
        confidence=result.confidence,
        camera_model=result.camera_model,
    )
    logger.info(
        "Camera calibration success: pitch=%.2f roll=%.2f fx=%.1f",
        outcome.pitch_deg,
        outcome.roll_deg,
        outcome.fx,
    )
    return outcome


def cache_dict_to_calibration_result(payload: dict[str, Any]) -> Any:
    """Build a TestModules calibration result from cached JSON."""
    calibration_result_cls = load_avroom_attr("CameraCalibrationResult", _CALIBRATION_MODULE)

    gravity_raw = payload.get("gravity", (0.0, 1.0, 0.0))
    gravity = tuple(float(v) for v in gravity_raw)
    return calibration_result_cls(
        gravity=(gravity[0], gravity[1], gravity[2]),
        roll_deg=float(payload.get("roll_deg", 0.0)),
        pitch_deg=float(payload.get("pitch_deg", 0.0)),
        fx=float(payload.get("fx", 0.0)),
        fy=float(payload.get("fy", 0.0)),
        cx=float(payload.get("cx", 0.0)),
        cy=float(payload.get("cy", 0.0)),
        confidence=(
            float(payload["confidence"]) if payload.get("confidence") is not None else None
        ),
        camera_model=str(payload.get("camera_model", "pinhole")),
    )
