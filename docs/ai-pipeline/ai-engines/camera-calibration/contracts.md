# Camera calibration contracts

## Input

| Field | Type | Notes |
|-------|------|-------|
| `image` | `np.ndarray` | BGR `uint8`, shape `(H, W, 3)` |

## Output

```python
@dataclass(frozen=True)
class CameraCalibrationResult:
    gravity: tuple[float, float, float]  # unit vector, downward in camera frame
    roll_deg: float
    pitch_deg: float
    fx: float
    fy: float
    cx: float
    cy: float
    confidence: float | None
    camera_model: str
```

## HTTP / disk cache

Session file: `{storage_dir}/{uid}_camera_calib.json` — JSON serialization of the fields above.

Calibration failure on upload is **non-fatal** (logged, upload still returns 200).
