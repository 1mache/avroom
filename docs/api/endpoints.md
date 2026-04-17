# API Endpoints

**File:** `fastApi-app/api/routes.py`

All endpoints are under the `/images` prefix.

---

## `POST /images/upload`

Uploads an image file and persists it to disk. Returns an `image_id` that identifies the stored image for subsequent click calls.

### Request

- **Content-Type:** `multipart/form-data`
- **Field:** `file` — the image file to upload (`UploadFile`)

### Response — `ImageUploadResponse`

```json
{
  "image_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "original_filename": "living_room.jpg",
  "stored_path": "/absolute/path/to/images/3fa85f64-....jpg"
}
```

| Field | Type | Description |
|---|---|---|
| `image_id` | `string` | Server-generated UUID; use this for click requests |
| `original_filename` | `string \| null` | Original client filename if provided |
| `stored_path` | `string \| null` | Absolute filesystem path (for debugging) |

### Behavior

1. Generates a UUID as `image_id`
2. Determines file extension from original filename (defaults to `.png` if unknown)
3. Writes raw bytes to `IMAGE_STORAGE_DIR/<image_id>.<ext>`
4. Returns the `ImageUploadResponse`

---

## `POST /images/click`

Processes a user's click on a previously uploaded image. Runs the full segmentation and inpainting pipeline, returning the background (object removed) and cutout (object extracted) as base64-encoded PNG images.

### Request Body — `ClickRequest`

```json
{
  "image_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "x": 420,
  "y": 315,
  "options": null
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `image_id` | `string` | Yes | UUID from the upload response |
| `x` | `int ≥ 0` | Yes | Click X coordinate in pixels (origin = top-left) |
| `y` | `int ≥ 0` | Yes | Click Y coordinate in pixels (origin = top-left) |
| `options` | `ImageProcessingOptions \| null` | No | Optional processing knobs |

### Response — `ClickResultResponse`

```json
{
  "image_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "background_b64": "<base64-encoded PNG>",
  "cutout_b64": "<base64-encoded PNG>",
  "format": "png"
}
```

| Field | Type | Description |
|---|---|---|
| `image_id` | `string` | Echoed from the request |
| `background_b64` | `string` | Base64 PNG of the scene with the object removed |
| `cutout_b64` | `string` | Base64 PNG of the extracted object (transparent background) |
| `format` | `string` | Image format used, always `"png"` |

The frontend uses these as data URLs: `data:image/png;base64,<background_b64>`.

### Error Responses

| Status | Condition |
|---|---|
| `500` | Image file not found for `image_id` (FileNotFoundError) |
| `500` | Pipeline error during segmentation or inpainting |

### Out-of-Bounds Clicks

If `x` or `y` fall outside the image dimensions, a warning is logged but processing continues. The pipeline receives the out-of-bounds coordinates; SAM will attempt to segment at that location.

---

## `ImageProcessingOptions`

Optional body field on the click endpoint. Currently defined but not meaningfully used by the pipeline:

| Field | Type | Default | Description |
|---|---|---|---|
| `output_format` | `string` | `"png"` | Desired output format (pipeline always returns PNG) |
| `grayscale` | `bool` | `false` | Convert to grayscale (not implemented in pipeline) |
