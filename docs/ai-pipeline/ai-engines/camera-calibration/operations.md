# Camera calibration operations

## Environment

| Variable | Default | Effect |
|----------|---------|--------|
| `CAMERA_CALIB` | `true` | Run GeoCalib on upload |

## Dependency

```bash
pip install -e "git+https://github.com/cvg/GeoCalib#egg=geocalib"
```

Listed in repo [`requirements.txt`](../../../../requirements.txt).

## Logging

| Point | Level |
|-------|-------|
| Calibrate start (shape) | INFO |
| Success (pitch, fx) | INFO |
| Failure on upload | WARNING |

## Cleanup

Session delete removes `{uid}_camera_calib.json` alongside depth caches.
