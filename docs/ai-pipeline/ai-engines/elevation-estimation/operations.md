# Elevation estimation operations

## Defaults

| Case | Behavior |
|------|----------|
| No calib cache | Level camera, HFOV 60° for fx/fy |
| Empty mask / depth | `elevation_deg = 15.0` |
| Geometric raw ≤ 0 with calibration | Scaled pitch hint in `[10, 22]` |
| Geometric raw ≤ 0 without calibration | `elevation_deg = 15.0` |
| Novel-view, no meta | Server uses `15.0` |

## Logging

| Point | Level |
|-------|-------|
| Estimate complete (elevation, used_calib) | INFO |
| Empty mask fallback | WARNING |

No separate env flag — always runs at object creation.
