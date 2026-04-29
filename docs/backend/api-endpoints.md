# API Endpoints

All routes are defined in [`fastApi-app/api/routes.py`](../../fastApi-app/api/routes.py) under the router `APIRouter(prefix="/images", tags=["images"])`.

| Method | Path | Request | Response | Handler |
|---|---|---|---|---|
| `GET` | `/` | — | `{"status": "ok", "service": "image-processing"}` | `read_root` in [`main.py`](../../fastApi-app/main.py) |
| `POST` | `/images/upload` | multipart/form-data with `file` | [`ImageUploadResponse`](schemas.md#imageuploadresponse) | `upload_image` in [`api/routes.py`](../../fastApi-app/api/routes.py) |
| `POST` | `/images/click` | JSON [`ClickRequest`](schemas.md#clickrequest) | [`ClickResultResponse`](schemas.md#clickresultresponse) | `handle_click` in [`api/routes.py`](../../fastApi-app/api/routes.py) |

## `POST /images/upload`

Defined at [`fastApi-app/api/routes.py`](../../fastApi-app/api/routes.py) lines 24–54.

**Request:**

- `Content-Type: multipart/form-data`
- Field `file`: the binary image (any image format Pillow can read).

**Behavior:**

1. Resolve the storage dir via `get_image_storage_dir()` (see [settings-and-storage.md](settings-and-storage.md)).
2. `mkdir -p` it.
3. Generate a fresh `image_id = str(uuid.uuid4())`.
4. Pick an extension from `file.filename` (lowercased) or fall back to `.png`.
5. Write the bytes to `{storage_dir}/{image_id}{suffix}`.
6. Return `ImageUploadResponse(image_id, original_filename, stored_path)`.

**Response example:**

```json
{
  "image_id": "f5e0edc4-fe7a-48bf-bd76-d706d32b61c1",
  "original_filename": "room.jpg",
  "stored_path": "C:/Avroom/avroom/fastApi-app/images/f5e0edc4-fe7a-48bf-bd76-d706d32b61c1.jpg"
}
```

**Notes:**

- The handler does **not** validate that the bytes are actually an image — that happens later, on the click request, when PIL tries to decode them.
- There is no size limit, no MIME check, no auth. This is a development-grade endpoint.

## `POST /images/click`

Defined at [`fastApi-app/api/routes.py`](../../fastApi-app/api/routes.py) lines 57–94.

**Request:**

- `Content-Type: application/json`
- Body: [`ClickRequest`](schemas.md#clickrequest) — `image_id`, `x`, `y` (both `>= 0`), and optional `options`.

**Behavior:**

1. Resolve the storage dir.
2. Call `process_click_on_image(image_id, base_dir, x, y, options)` in [`fastApi-app/core/image_processing.py`](../../fastApi-app/core/image_processing.py). See [core-image-processing.md](core-image-processing.md).
3. Catch `ValueError` → HTTP 422; catch `FileNotFoundError` and bare `Exception` → HTTP 500 with the exception message in `detail`.
4. Base64-encode the returned `background_bytes` and `cutout_bytes` (PNG).
5. Return `ClickResultResponse(image_id, background_b64, cutout_b64, format)` where `format` is currently always `"png"`.

**Response example (truncated):**

```json
{
  "image_id": "f5e0edc4-...",
  "background_b64": "iVBORw0KGgoAAAANSUhEUg...",
  "cutout_b64": "iVBORw0KGgoAAAANSUhEUg...",
  "format": "png"
}
```

**Coordinate system:** `(x, y)` are pixels with origin at the **top-left** of the original (natural) image. The frontend takes care of scaling display clicks back to natural coordinates — see [frontend/user-flow.md](../frontend/user-flow.md).

**Error mapping:**

| Backend exception | HTTP status | Source |
|---|---|---|
| `ValueError` (out-of-bounds, invalid image bytes) | 422 | [`api/routes.py`](../../fastApi-app/api/routes.py) lines 76–78 |
| `FileNotFoundError` (no stored file for `image_id`) | 500 | [`api/routes.py`](../../fastApi-app/api/routes.py) lines 79–81 |
| anything else (model errors, encoding failures) | 500 | [`api/routes.py`](../../fastApi-app/api/routes.py) lines 82–84 |

## `GET /`

Health/info endpoint defined inline in [`fastApi-app/main.py`](../../fastApi-app/main.py) lines 25–29.

```json
{ "status": "ok", "service": "image-processing" }
```
