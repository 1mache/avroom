# Novel view contracts

- **Inputs:** Flexible image representations accepted by `to_pil_rgba`, plus keyword args on `synthesize`:
  - `elevation_deg` — absolute elevation of the **source** view (degrees)
  - `azimuth_deg` — relative azimuth to the **target** view (degrees)
  - `relative_elevation_deg` — relative elevation delta (default `0`)
  - `radius` — optional zoom / distance (default `0` = model default)
  - `seed` — RNG seed (default `0`)
- **Outputs:** uint8 `numpy.ndarray` shape `(H, W, 4)` in **BGRA** channel order (OpenCV convention), matching existing cutout PNG layout.

## HTTP contract

**Request** (`POST /images/novel-view`):

| Field | Type | Required |
|-------|------|----------|
| `uid` | `str` | yes |
| `object_id` | `int` (≥ 0) | yes |
| `elevation_deg` | `float` | yes |
| `azimuth_deg` | `float` | yes |
| `relative_elevation_deg` | `float` | no (default `0`) |
| `radius` | `float` | no (default `0`) |
| `seed` | `int` | no (default `0`) |

The client does **not** upload the cutout; the server resolves it from disk.

**Response** (JSON):

| Field | Type |
|-------|------|
| `uid`, `object_id` | echoed |
| `image_b64` | base64 PNG |
| `format` | `"png"` |
| `cutout_bounds` | `CutoutBounds \| null` |
| pose fields | echoed |

**Status codes:** `200` success, `404` missing cutout, `422` validation, `500` inference failure.

## Anti-patterns

- Do **not** implement as `Reconstruction3DStrategy` (returns GLB, not 2D).
- Do **not** feed the full room photo — use the object cutout only.
