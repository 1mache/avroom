# Camera calibration

**What this is:** Single-image camera calibration via GeoCalib. Estimates gravity direction (roll/pitch) and pinhole intrinsics from one room photo.

**When it runs:** On `POST /images/upload` after the image is stored, via inference pool `CALIBRATE_CAMERA` job (when `CAMERA_CALIB=true`).

**Not wired into:** `ObjectRemover`, segment/inpaint pipelines.

**In one line:** BGR room photo in → `CameraCalibrationResult` (gravity + K) → cached as `{uid}_camera_calib.json`.

Code: [`TestModules/src/ai_engines/camera_calibration/`](../../../../TestModules/src/ai_engines/camera_calibration/).

## Detail pages

- [components.md](components.md)
- [flow.md](flow.md)
- [contracts.md](contracts.md)
- [operations.md](operations.md)

Parent: [ai-engines/README.md](../README.md).
