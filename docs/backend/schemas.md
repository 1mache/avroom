# Pydantic Schemas

All defined in [`fastApi-app/schemas/image.py`](../../fastApi-app/schemas/image.py).

## Sessions

`SessionInfo` is returned by `GET /images/sessions` and `POST /images/{uid}/name`.

| Field | Type | Description |
|---|---|---|
| `uid` | `str` | Session UUID. |
| `name` | `str \| null` | Human-readable label, or `null` if unnamed. |

`SetNameRequest` is the body of `POST /images/{uid}/name`.

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Desired label (min length 1). |

## Upload

`ImageUploadResponse` is returned by `POST /images/upload`.

| Field | Type | Description |
|---|---|---|
| `image_id` | `str` | Server UUID used by later requests. |
| `original_filename` | `str \| null` | Filename sent by client. |
| `stored_path` | `str \| null` | Debug filesystem path. |

## Segmentation

`SegmentRequest` extends `ClickRequest`: `image_id`, natural-image `x/y`, optional `options`.

`SegmentResponse` returns:

| Field | Type | Description |
|---|---|---|
| `image_id` | `str` | Segmented image id. |
| `masks` | `list[SegmentMaskOption]` | User-selectable candidates in SAM return order. |

`SegmentMaskOption`:

| Field | Type | Description |
|---|---|---|
| `mask_id` | `str` | Candidate id; currently candidate index as string. |
| `cutout_b64` | `str` | BGRA cutout preview, not raw black-white mask. |
| `format` | `str` | Currently `png`. |
| `cutout_bounds` | `CutoutBounds \| null` | Visible-object bounds for preview and later drag. |

## Inpainting

`InpaintMaskRequest` is sent to `POST /images/inpaint`.

| Field | Type | Description |
|---|---|---|
| `image_id` | `str` | Uploaded image id. |
| `mask_id` | `str` | Selected candidate id from segmentation response. |

`InpaintMaskResponse` extends `ClickResultResponse` (`image_id`, `background_b64`, `cutout_b64`, `format`, `cutout_bounds`) and adds:

| Field | Type | Description |
|---|---|---|
| `object_id` | `int` | Zero-based integer id assigned to the newly created object within the session. Defaults to `0` if the inpaint route does not supply one (legacy behavior). |

## Object List

`ObjectInfo` describes one finalized object within a session. Returned inside `ObjectListResponse` by `GET /images/{uid}/objects`.

| Field | Type | Description |
|---|---|---|
| `object_id` | `int` | Zero-based integer id. |
| `cutout_b64` | `str` | Base64-encoded BGRA cutout PNG. |
| `format` | `str` | Currently `png`. |
| `cutout_bounds` | `CutoutBounds \| null` | Tight visible-object bounds inside the cutout PNG. |
| `has_3d` | `bool` | Whether a GLB 3D model has been generated for this object. |

`ObjectListResponse` is returned by `GET /images/{uid}/objects`.

| Field | Type | Description |
|---|---|---|
| `uid` | `str` | Session UID. |
| `objects` | `list[ObjectInfo]` | Objects in ascending `object_id` order. |

## Final Result Metadata

`CutoutBounds` describes visible object inside full-size cutout PNG:

| Field | Type | Meaning |
|---|---|---|
| `left` | `int` | First visible pixel column, inclusive. |
| `top` | `int` | First visible pixel row, inclusive. |
| `right` | `int` | First pixel column after visible object, exclusive. |
| `bottom` | `int` | First pixel row after visible object, exclusive. |
| `natural_width` | `int` | Full cutout PNG width. |
| `natural_height` | `int` | Full cutout PNG height. |

`UidCacheStatusResponse` reports final cached artifacts and `cutout_bounds` for restored sessions.

| Field | Type | Description |
|---|---|---|
| `uid` | `str` | Session UUID. |
| `name` | `str \| null` | Human-readable label from `names.json`, or `null`. |
| `has_background` | `bool` | Background PNG cached on disk. |
| `has_cutout` | `bool` | Cutout PNG cached on disk. |
| `has_3d` | `bool` | GLB model cached on disk. |
| `cutout_bounds` | `CutoutBounds \| null` | Tight visible-object bounds from cached cutout. |

## Legacy

`ClickRequest` and `ClickResultResponse` remain for `POST /images/click`, but normal frontend flow uses `SegmentRequest` followed by `InpaintMaskRequest`.

Frontend mirrors these types in [`react-front/src/types/api.ts`](../../react-front/src/types/api.ts). No codegen exists.
