# Novel view contracts

- **Inputs:** Flexible image representations accepted by `to_pil_rgba`, plus keyword args on `synthesize`:
  - `elevation_deg` — absolute elevation of the **source** view (degrees); used by Zero123; accepted but unused for mesh orbit camera placement
  - `azimuth_deg` — relative azimuth to the **target** view (degrees)
  - `relative_elevation_deg` — relative elevation delta (default `0`)
  - `radius` — optional zoom / distance (default `0` = model/orbit default)
  - `mesh` — optional GLB (`bytes` / path). Ignored by Zero123; required by `MeshRenderNovelViewStrategy` unless a `Reconstruction3DFacade` was injected for fallback generation
- **Outputs:** uint8 `numpy.ndarray` shape `(H, W, 4)` in **BGRA** channel order (OpenCV convention), matching existing cutout PNG layout.
- **RNG seed:** fixed at `0` for HTTP requests (not exposed on the API). Mesh render is deterministic and ignores `seed`.

## HTTP contract

**Request** (`POST /images/novel-view`):

| Field | Type | Required |
|-------|------|----------|
| `uid` | `str` | yes |
| `object_id` | `int` (≥ 0) | yes |
| `elevation_deg` | `float` | yes |
| `azimuth_deg` | `float` | yes |
| `azimuth_direction` | `"CLOCKWISE"` \| `"C_CLOCKWISE"` | no |
| `relative_elevation_deg` | `float` | no (default `0`) |
| `elevation_direction` | `"UP"` \| `"DOWN"` | no |
| `radius` | `float` | no (default `0`) |
| `zoom_direction` | `"ZOOM_IN"` \| `"ZOOM_OUT"` | no |

The client does **not** upload the cutout or GLB; the server resolves the cutout from disk and ensures a GLB at `tmp/3d/{uid}_{object_id}.glb` (generate via `Reconstruction3DFacade` on miss) before mesh-rendering.

### Pose direction adapter (HTTP)

Optional direction fields are normalized by `NovelViewRotationAdapter` before inference:

| Axis | Direction field | Magnitude field | Signed result |
|------|-----------------|-----------------|---------------|
| Azimuth | `azimuth_direction` | `azimuth_deg` | `CLOCKWISE` → `+`, `C_CLOCKWISE` → `-` (viewed from above) |
| Elevation delta | `elevation_direction` | `relative_elevation_deg` | `UP` → `+`, `DOWN` → `-` |
| Zoom / radius | `zoom_direction` | `radius` | `ZOOM_OUT` → `+` (farther), `ZOOM_IN` → `-` (closer) |

Rules:

- **No direction on an axis:** the supplied signed value is passed through unchanged (backward compatible).
- **Direction supplied:** the magnitude must be a finite non-negative number; negative magnitudes return **422**.
- **Response:** echoes optional direction fields and returns the **resolved signed** `azimuth_deg`, `relative_elevation_deg`, and `radius` actually sent to the mesh renderer (HTTP) / Zero123 (direct facade).

Python named magnitudes (optional, for readability):

- Azimuth: `FRONT=0`, `QUARTER=45`, `SIDE=90`, `THREE_QUARTER=135`, `BACK=180`
- Elevation: `LEVEL=0`, `LOW_TILT=15`, `HIGH_TILT=45`
- Zoom: `NO_ZOOM=0`, `ZOOM_STEP=0.5`

**Response** (JSON):

| Field | Type |
|-------|------|
| `uid`, `object_id` | echoed |
| `image_b64` | base64 PNG |
| `format` | `"png"` |
| `cutout_bounds` | `CutoutBounds \| null` |
| `elevation_deg` | echoed (source view; no direction adapter, no snapping) |
| `azimuth_deg`, `relative_elevation_deg` | resolved signed values, **snapped** to the nearest 10° (see below) |
| `radius` | resolved signed value (never snapped) |
| `azimuth_direction`, `elevation_direction`, `zoom_direction` | echoed when supplied |

**Status codes:** `200` success, `404` missing cutout, `422` validation, `500` inference failure.

### HTTP-layer pose snapping and cache

After the direction adapter resolves signed values, `POST /images/novel-view` additionally snaps `azimuth_deg` and `relative_elevation_deg` onto a 10° grid (`ROTATION_STEP_DEG`) and wraps azimuth into `(-180, 180]`, **before** consulting the disk cache described in [operations.md](operations.md#disk-cache) or invoking the model. This is deliberately an HTTP-only step — it lives in `fastApi-app/api/novel_view.py`, not in `NovelViewRotationAdapter` — so a UI that lets the pose vary continuously (e.g. free camera orbit) still collapses onto a small set of cache keys instead of triggering fresh inference on every near-identical request. `radius` is never snapped. The response's `azimuth_deg`/`relative_elevation_deg` are the snapped values actually sent to the model, not the raw request.

## Anti-patterns

- Do **not** implement as `Reconstruction3DStrategy` (returns GLB, not 2D).
- Do **not** feed the full room photo — use the object cutout only.
- Do **not** send a negative magnitude together with a direction on the same axis — use signed values without a direction instead.
