# Pydantic Schemas

All defined in [`fastApi-app/schemas/image.py`](../../fastApi-app/schemas/image.py).

## `ImageProcessingOptions`

Optional knobs passed with click requests. Still mostly reserved.

| Field | Type | Default | Description |
|---|---|---|---|
| `output_format` | `str` | `"png"` | Desired output format. Current pipeline still returns PNG. |
| `grayscale` | `bool` | `False` | Reserved flag. |

## `ImageUploadResponse`

Returned by `POST /images/upload`.

| Field | Type | Description |
|---|---|---|
| `image_id` | `str` | Server-generated UUID used by later requests. |
| `original_filename` | `str \| null` | Filename sent by client, if any. |
| `stored_path` | `str \| null` | Debug-oriented filesystem path. |

## `ClickRequest`

Body of `POST /images/click`.

| Field | Type | Constraints | Description |
|---|---|---|---|
| `image_id` | `str` | required | UID from upload. |
| `x` | `int` | `>= 0` | Natural-image X coordinate. |
| `y` | `int` | `>= 0` | Natural-image Y coordinate. |
| `options` | `ImageProcessingOptions \| null` | optional | Reserved processing options. |

Schema only enforces non-negative values. Real image bounds are checked later in processing code.

## `CutoutBounds`

New metadata schema used by drag/clamp behavior.

| Field | Type | Meaning |
|---|---|---|
| `left` | `int` | First visible pixel column, inclusive. |
| `top` | `int` | First visible pixel row, inclusive. |
| `right` | `int` | First pixel column after visible object, exclusive. |
| `bottom` | `int` | First pixel row after visible object, exclusive. |
| `natural_width` | `int` | Full cutout PNG width. |
| `natural_height` | `int` | Full cutout PNG height. |

Important contract:

- Bounds describe the visible object inside the full cutout PNG.
- They are not frame coordinates.
- Frontend uses them to clamp translation so transparent padding may leave frame while opaque object stays inside frame.

## `ClickResultResponse`

Returned by `POST /images/click`.

| Field | Type | Description |
|---|---|---|
| `image_id` | `str` | Echo of request UID. |
| `background_b64` | `str` | Base64 PNG of inpainted background. |
| `cutout_b64` | `str` | Base64 BGRA PNG of segmented object. |
| `format` | `str` | Current image encoding, still `"png"`. |
| `cutout_bounds` | `CutoutBounds \| null` | Tight visible-object bounds extracted from cutout alpha. |

`cutout_bounds` may be `null` if server cannot decode the PNG for metadata extraction. Frontend should handle that by falling back to full-image clamping.

## `UidCacheStatusResponse`

Returned by `GET /images/{uid}/cache`.

| Field | Type | Description |
|---|---|---|
| `uid` | `str` | Requested UID. |
| `has_background` | `bool` | `{uid}_background.png` exists. |
| `has_cutout` | `bool` | `{uid}_cutout.png` exists. |
| `has_3d` | `bool` | `{uid}.glb` exists. |
| `cutout_bounds` | `CutoutBounds \| null` | Bounds derived from cached cutout PNG, if present. |

This extra metadata lets session restore recover drag bounds without re-running segmentation.

## Frontend mirror

Frontend re-declares these types in [`react-front/src/types/api.ts`](../../react-front/src/types/api.ts). No codegen exists. Backend schema changes must be mirrored manually.
