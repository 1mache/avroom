# API Schemas

**File:** `fastApi-app/schemas/image.py`

All models use Pydantic v2 `BaseModel` with typed, annotated fields.

---

## `ImageUploadResponse`

Returned by `POST /images/upload`.

| Field | Type | Description |
|---|---|---|
| `image_id` | `str` | Server-generated UUID for the stored image |
| `original_filename` | `str \| None` | Client filename if provided; `None` otherwise |
| `stored_path` | `str \| None` | Absolute filesystem path to the saved file (for debugging) |

---

## `ClickRequest`

Request body for `POST /images/click`.

| Field | Type | Constraint | Description |
|---|---|---|---|
| `image_id` | `str` | — | References a previously uploaded image |
| `x` | `int` | `≥ 0` | Pixel X coordinate from the left edge |
| `y` | `int` | `≥ 0` | Pixel Y coordinate from the top edge |
| `options` | `ImageProcessingOptions \| None` | default `None` | Optional processing configuration |

---

## `ClickResultResponse`

Returned by `POST /images/click`.

| Field | Type | Description |
|---|---|---|
| `image_id` | `str` | Echoed from the request |
| `background_b64` | `str` | Base64-encoded PNG: the scene with the object removed |
| `cutout_b64` | `str` | Base64-encoded PNG: the removed object on a transparent background |
| `format` | `str` | Image format (`"png"` currently always) |

The base64 strings can be used directly as data URLs:
```
data:image/png;base64,<background_b64>
data:image/png;base64,<cutout_b64>
```

---

## `ImageProcessingOptions`

Optional knobs attached to `ClickRequest.options`. Currently defined for forward compatibility but not actively used by the pipeline.

| Field | Type | Default | Description |
|---|---|---|---|
| `output_format` | `str` | `"png"` | Desired output format |
| `grayscale` | `bool` | `False` | Convert output to grayscale |
