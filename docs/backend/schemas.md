# Pydantic Schemas

All defined in [`fastApi-app/schemas/image.py`](../../fastApi-app/schemas/image.py).

## `ImageProcessingOptions`

Optional knobs passed alongside a click. Currently unused inside `ObjectRemover.remove_object` — see the note in [core-image-processing.md](core-image-processing.md).

| Field | Type | Default | Description |
|---|---|---|---|
| `output_format` | `str` | `"png"` | Desired output format. Pipeline currently ignores it. |
| `grayscale` | `bool` | `False` | Whether to convert the output to grayscale. Pipeline currently ignores it. |

## `ImageUploadResponse`

Returned by `POST /images/upload`.

| Field | Type | Description |
|---|---|---|
| `image_id` | `str` | Server-generated UUID. The frontend must keep this to make later click requests. |
| `original_filename` | `str \| null` | Filename the client sent, if any. |
| `stored_path` | `str \| null` | Absolute path on the server (for debugging only). |

## `ClickRequest`

Body of `POST /images/click`.

| Field | Type | Constraints | Description |
|---|---|---|---|
| `image_id` | `str` | required | Returned by a prior upload. |
| `x` | `int` | `>= 0` (`Field(ge=0)`) | Pixel X in **natural** image coordinates, origin top-left. |
| `y` | `int` | `>= 0` (`Field(ge=0)`) | Pixel Y in natural coordinates. |
| `options` | `ImageProcessingOptions \| null` | optional | See above. Reserved. |

The upper bounds on `x` / `y` are not enforced at the schema level — the bounds check happens inside `process_click_on_image` and produces a 422 if the click is outside the image.

## `ClickResultResponse`

Returned by `POST /images/click`.

| Field | Type | Description |
|---|---|---|
| `image_id` | `str` | Echoed back from the request. |
| `background_b64` | `str` | Base64-encoded PNG of the original image with the clicked object removed and the hole inpainted. |
| `cutout_b64` | `str` | Base64-encoded **BGRA** PNG of the clicked object on a transparent background. |
| `format` | `str` | Always `"png"` today; the field exists in case the pipeline gains other encodings. |

## `UidCacheStatusResponse`

Returned by `GET /images/{uid}/cache`.

| Field | Type | Description |
|---|---|---|
| `uid` | `str` | The requested UID. |
| `has_background` | `bool` | `{uid}_background.png` exists on disk. |
| `has_cutout` | `bool` | `{uid}_cutout.png` exists on disk. |
| `has_3d` | `bool` | `{uid}.glb` exists in the 3D storage dir. |

## Frontend mirror

The frontend re-declares these in TypeScript at [`react-front/src/types/api.ts`](../../react-front/src/types/api.ts). When you change a Pydantic model here, update that file as well — there is no codegen.
