# Elevation estimation contracts

## Input

| Field | Type | Notes |
|-------|------|-------|
| `depth_map` | `np.ndarray` | `(H, W)` or `(H, W, 1)` uint8 relative depth |
| `mask` | `np.ndarray` | Binary/refined object mask |
| `calibration` | `CameraCalibrationResult \| None` | Session cache from upload |

## Output

```python
@dataclass(frozen=True)
class ElevationEstimationResult:
    elevation_deg: float   # Zero123 source elevation, clamped [-10, 80]
    used_calibration: bool
```

## Persistence

Stored on `ObjectMetadata.source_elevation_deg` at inpaint time. Novel-view reads this value (fallback `15.0`).
