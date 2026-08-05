# Elevation estimation components

| Component | Role |
|-----------|------|
| `ElevationEstimationStrategy` | ABC — `estimate(depth, mask, calibration?) -> ElevationEstimationResult` |
| `GeometricElevationEstimationStrategy` | Default: 3D center from masked depth, angle vs gravity-up |
| `ElevationEstimationFacade` | Public entry point |

Consumes cached `CameraCalibrationResult` from upload; does not run GeoCalib itself.
