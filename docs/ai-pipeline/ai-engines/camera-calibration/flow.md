# Camera calibration flow

1. Upload stores room photo under `{uid}.{ext}`.
2. If `CAMERA_CALIB=true`, FastAPI submits `CALIBRATE_CAMERA` to the inference pool.
3. Worker decodes bytes → BGR, calls `CameraCalibrationFacade.calibrate`.
4. Result written to `{uid}_camera_calib.json`.
5. Later, elevation estimation loads this cache once per session when creating objects.

GeoCalib runs one forward pass + internal LM optimization (~100 ms GPU).
