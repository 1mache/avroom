# Camera calibration components

| Component | Role |
|-----------|------|
| `CameraCalibrationStrategy` | ABC — `calibrate(image) -> CameraCalibrationResult` |
| `GeoCalibCameraCalibrationStrategy` | Default backend wrapping GeoCalib |
| `CameraCalibrationFacade` | Stable public entry; holds one strategy |
| `CameraCalibrationResult` | Frozen dataclass: gravity, roll/pitch, fx/fy/cx/cy |

FastAPI persists results via [`fastApi-app/core/camera_calib_cache.py`](../../../../fastApi-app/core/camera_calib_cache.py).
