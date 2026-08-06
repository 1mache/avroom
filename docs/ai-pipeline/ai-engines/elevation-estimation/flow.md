# Elevation estimation flow

1. Load `{uid}_camera_calib.json` if present (optional).
2. Load depth map from session depth cache (same canvas hash as segment).
3. Load refined mask for the selected candidate.
4. Back-project masked pixels with K (from calib or default HFOV 60°).
5. Object center `C` = mean of 3D points; camera at origin.
6. `up = -normalize(gravity)` or `(0, -1, 0)` without calib.
7. `elevation_deg = asin(dot(normalize(-C), up))` in degrees, clamped.
8. Save on object metadata as `source_elevation_deg`.

Assumes upright furniture (object up ≈ gravity up).
