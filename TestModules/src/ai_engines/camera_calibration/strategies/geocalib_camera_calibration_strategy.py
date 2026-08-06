from __future__ import annotations

import logging
import math

import cv2
import numpy as np

from ..camera_calibration_result import CameraCalibrationResult
from ..camera_calibration_strategy import CameraCalibrationStrategy

logger = logging.getLogger(__name__)


class GeoCalibCameraCalibrationStrategy(CameraCalibrationStrategy):
    """Single-image calibration via GeoCalib (ECCV 2024).

    Lazy-loads the GeoCalib model on first ``calibrate`` call. Expects BGR
    ``uint8`` input and returns gravity plus pinhole intrinsics.
    """

    def __init__(
        self,
        *,
        weights: str = "pinhole",
        device: str | None = None,
    ) -> None:
        self._weights = weights
        self._device = device
        self._model: object | None = None
        logger.info(
            "GeoCalibCameraCalibrationStrategy configured (weights=%s device=%s)",
            weights,
            device or "auto",
        )

    def _resolve_device(self) -> str:
        if self._device is not None:
            return self._device
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except ModuleNotFoundError:
            return "cpu"

    def _ensure_model(self) -> object:
        if self._model is not None:
            return self._model

        try:
            from geocalib import GeoCalib
        except ModuleNotFoundError as exc:
            logger.error("GeoCalib import failed: %s", exc)
            raise RuntimeError(
                "GeoCalib is required for camera calibration. "
                "Install with: pip install -e \"git+https://github.com/cvg/GeoCalib#egg=geocalib\""
            ) from exc

        device = self._resolve_device()
        logger.info("Loading GeoCalib (weights=%s) onto %s", self._weights, device)
        model = GeoCalib(weights=self._weights).to(device)
        self._model = model
        logger.info("GeoCalib loaded successfully")
        return self._model

    @staticmethod
    def _to_degrees(value: float) -> float:
        if not math.isfinite(value):
            return 0.0
        if abs(value) <= math.pi + 1e-3:
            return math.degrees(value)
        return value

    def calibrate(self, image: np.ndarray) -> CameraCalibrationResult:
        """Run GeoCalib on ``image`` and map outputs to :class:`CameraCalibrationResult`."""
        if image.ndim != 3 or image.shape[2] != 3:
            raise ValueError("Camera calibration expects a BGR uint8 image with shape (H, W, 3).")

        try:
            import torch
        except ModuleNotFoundError as exc:
            raise RuntimeError("PyTorch is required for GeoCalib camera calibration.") from exc

        model = self._ensure_model()
        device = self._resolve_device()

        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        tensor = torch.from_numpy(rgb).permute(2, 0, 1).float().div(255.0).unsqueeze(0).to(device)

        logger.info("GeoCalib calibrate start: shape=%s", image.shape)
        with torch.inference_mode():
            result = model.calibrate(tensor[0])

        gravity_obj = result["gravity"]
        camera_obj = result["camera"]

        gravity_vec = gravity_obj.vec3d.detach().cpu().numpy().reshape(-1)
        if gravity_vec.shape[0] != 3:
            raise RuntimeError(f"Unexpected GeoCalib gravity shape: {gravity_vec.shape}")

        norm = float(np.linalg.norm(gravity_vec))
        if norm <= 1e-8:
            raise RuntimeError("GeoCalib returned a zero gravity vector.")
        gravity_unit = tuple((gravity_vec / norm).astype(float).tolist())

        roll_deg = self._to_degrees(float(gravity_obj.roll))
        pitch_deg = self._to_degrees(float(gravity_obj.pitch))

        focal = camera_obj.f.detach().cpu().numpy().reshape(-1)
        principal = camera_obj.c.detach().cpu().numpy().reshape(-1)
        if focal.size < 2 or principal.size < 2:
            raise RuntimeError("GeoCalib returned unexpected camera intrinsics shape.")
        fx = float(focal[0])
        fy = float(focal[1])
        cx = float(principal[0])
        cy = float(principal[1])

        confidence: float | None = None
        if "gravity_confidence" in result:
            confidence = float(result["gravity_confidence"])

        logger.info(
            "GeoCalib calibrate complete: pitch=%.2f roll=%.2f fx=%.1f fy=%.1f",
            pitch_deg,
            roll_deg,
            fx,
            fy,
        )

        return CameraCalibrationResult(
            gravity=gravity_unit,  # type: ignore[arg-type]
            roll_deg=roll_deg,
            pitch_deg=pitch_deg,
            fx=fx,
            fy=fy,
            cx=cx,
            cy=cy,
            confidence=confidence,
            camera_model="pinhole",
        )
