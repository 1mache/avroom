# Pydantic Schemas

All defined in [`fastApi-app/schemas/image.py`](../../fastApi-app/schemas/image.py).

## Sessions

`SessionInfo` is returned by `GET /images/sessions` and `POST /images/{uid}/name`.

| Field | Type | Description |
|---|---|---|
| `uid` | `str` | Session UUID. |
| `name` | `str \| null` | Human-readable label, or `null` if unnamed. |
| `last_changed` | `str \| null` | ISO-8601 UTC timestamp of the last client-visible session mutation, or `null` when absent. |

`SetNameRequest` is the body of `POST /images/{uid}/name`.

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Desired label (min length 1). |

`SessionSyncCheckRequest` is the body of `POST /images/{uid}/sync-check`.

| Field | Type | Description |
|---|---|---|
| `client_last_changed` | `str \| null` | ISO-8601 UTC timestamp the client believes is current; `null` when unknown. |

`SessionSyncCheckResponse` is returned by `POST /images/{uid}/sync-check`.

| Field | Type | Description |
|---|---|---|
| `last_changed` | `str` | Server-side last-changed timestamp. Empty string when the session exists but has no recorded timestamp yet. |
| `needs_refresh` | `bool` | `true` when the client must re-poll session data from the server. |

`SessionPreviewRequest` is the body of `POST /images/{uid}/preview`.

| Field | Type | Description |
|---|---|---|
| `image_b64` | `str` | Base64-encoded preview JPEG, no `data:` prefix (min length 1). |

## Upload

`ImageUploadResponse` is returned by `POST /images/upload`.

| Field | Type | Description |
|---|---|---|
| `image_id` | `str` | Server UUID used by later requests. |
| `original_filename` | `str \| null` | Filename sent by client. |
| `stored_path` | `str \| null` | Debug filesystem path. |
| `last_changed` | `str` | ISO-8601 UTC timestamp recorded when the session was created. |

## Segmentation

`SegmentRequest` extends `ClickRequest`: `image_id`, natural-image `x/y`, optional `options`, and `verify` (`manual` default, or `auto`).

`SegmentResponse` returns:

| Field | Type | Description |
|---|---|---|
| `image_id` | `str` | Segmented image id. |
| `masks` | `list[SegmentMaskOption]` | User-selectable candidates in SAM return order. `verify=auto` returns one winner. |

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
| `verify` | `manual` \| `auto` | Accepted for symmetry with segment; auto inpaint retry is not implemented yet. Default `manual`. |

`InpaintMaskResponse` extends `ClickResultResponse` (`image_id`, `background_b64`, `cutout_b64`, `format`, `cutout_bounds`) and adds:

| Field | Type | Description |
|---|---|---|
| `object_id` | `int` | Zero-based integer id assigned to the newly created object within the session. |
| `object_uuid` | `str` | Server-generated UUID; primary searchable key for object metadata endpoints. |

## Object Metadata

`ObjectMetadataResponse` is returned by `GET /images/objects/{object_uuid}`, `PATCH /images/objects/{object_uuid}`, and `setObjectName`/`setObjectOffset` on the frontend.

| Field | Type | Description |
|---|---|---|
| `uuid` | `str` | Server-generated UUID. |
| `session_id` | `str` | Session UID (same as upload `image_id`). |
| `object_id` | `int` | Zero-based integer id within the session. |
| `name` | `str \| null` | Optional human-readable label. |
| `average_depth` | `float` | Mean uint8 depth over the mask at creation (updated after rescale-by-depth). |
| `content_hash` | `str` | SHA-256 hex of canvas bytes when the object was created. |
| `created_at` | `str` | ISO-8601 UTC timestamp. |
| `has_3d` | `bool` | Whether a GLB exists for this object. |
| `cutout_bounds` | `CutoutBounds \| null` | Derived from on-disk cutout PNG alpha. |
| `offset_x` | `float` | Persisted drag offset X, natural-image pixels. `0.0` until dragged. |
| `offset_y` | `float` | Persisted drag offset Y, natural-image pixels. `0.0` until dragged. |

`UpdateObjectRequest` is the body of `PATCH /images/objects/{object_uuid}` — a partial update, every field independently optional.

| Field | Type | Description |
|---|---|---|
| `name` | `str \| null` | New label, or `null` to clear. Omit the field to leave it unchanged. |
| `offset_x` | `float \| null` | New drag offset X. Omit to leave unchanged. |
| `offset_y` | `float \| null` | New drag offset Y. Omit to leave unchanged. |

The handler reads `request.model_fields_set` (which keys were actually present in the JSON body) rather than trusting `None` defaults, since `name`'s `None` means "clear" while `offset_x`/`offset_y`'s `None` means "not sent" — two different meanings on the same request model.

`DuplicateObjectResponse` is returned by `POST /images/objects/{object_uuid}/duplicate`.

| Field | Type | Description |
|---|---|---|
| `object_uuid` | `str` | Server-generated UUID of the newly cloned object. |

## Rescale by Depth

`RescaleByDepthRequest` is sent to `POST /images/objects/{object_uuid}/rescale-by-depth`.

| Field | Type | Description |
|---|---|---|
| `x` | `int` | Placement X in natural-image pixels (`ge=0`). |
| `y` | `int` | Placement Y in natural-image pixels (`ge=0`). |

`RescaleByDepthResponse`:

| Field | Type | Description |
|---|---|---|
| `object_uuid` | `str` | Object UUID. |
| `session_id` | `str` | Session UID. |
| `object_id` | `int` | Zero-based object id. |
| `source_average_depth` | `float` | `average_depth` before this rescale. |
| `target_depth` | `float` | Sampled uint8 depth at placement point. |
| `scale_factor` | `float` | Applied factor (`target_depth / source_average_depth`). |
| `cutout_b64` | `str` | Base64 rescaled BGRA cutout PNG. |
| `format` | `str` | Currently `png`. |
| `cutout_bounds` | `CutoutBounds \| null` | Bounds after rescale. |

## Object List

`ObjectInfo` describes one finalized object within a session. Returned inside `ObjectListResponse` by `GET /images/{uid}/objects`.

| Field | Type | Description |
|---|---|---|
| `object_id` | `int` | Zero-based integer id. |
| `uuid` | `str \| null` | Server UUID from metadata, if persisted. |
| `name` | `str \| null` | Optional label. |
| `average_depth` | `float \| null` | Mean uint8 depth over mask at creation. |
| `cutout_b64` | `str` | Base64-encoded BGRA cutout PNG. |
| `format` | `str` | Currently `png`. |
| `cutout_bounds` | `CutoutBounds \| null` | Tight visible-object bounds inside the cutout PNG. |
| `has_3d` | `bool` | Whether a GLB 3D model has been generated for this object. |
| `offset_x` | `float` | Persisted drag offset X, natural-image pixels. |
| `offset_y` | `float` | Persisted drag offset Y, natural-image pixels. |

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

## Debug

Defined in [`fastApi-app/schemas/debug.py`](../../fastApi-app/schemas/debug.py) — kept separate from `schemas/image.py` since these back the `/debug` router only (see [api-endpoints.md](api-endpoints.md#debug-endpoints)).

`DebugCheckResult` — one technical or content validation check's outcome.

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Check identifier, e.g. `blur` or `exposure`. |
| `passed` | `bool` | Whether this check passed. |
| `score` | `float \| null` | Check-specific numeric score, if any. Always `null` for content checks — `checks` and `scores` in `ContentValidationOutcome` use unrelated key namespaces (e.g. `scene_space_or_landscape` vs `scene_p`) with no declared mapping. |
| `message` | `str` | Human-readable detail, populated mainly on failure. |

`DebugValidationResponse` is returned by `POST /debug/validate`.

| Field | Type | Description |
|---|---|---|
| `ok` | `bool` | True iff every technical and content check passed. |
| `technical_ok` | `bool` | True iff every technical check passed. |
| `content_ok` | `bool \| null` | True/False if content validation ran; `null` if skipped (decode failure). |
| `technical` | `list[DebugCheckResult]` | Every technical check, in run order. |
| `content` | `list[DebugCheckResult]` | Every content (CLIP) check, if it ran; empty list when skipped. |
| `content_skipped_reason` | `str \| null` | Why the content stage didn't run, if it didn't. |
| `elapsed_ms` | `float` | Total wall time for both stages. |

`DebugAutoMaskPickResponse` is returned by `POST /debug/auto-mask-pick`: `click_xy`, `threshold`, `winner_index`, `candidates` (`index`, `score`, `reason`, `preview_b64`, `clip_crop_b64`, `cutout_b64`), `elapsed_ms`.

`DebugInpaintVerifyResponse` is returned by `POST /debug/inpaint-verify`: `click_xy`, `mask_index`, `passed`, `retries_exhausted`, `lama_b64`, `final_b64`, `attempts` (each with `ok`, CLIP `scores`/`winner_label`, `params` as `DebugSdParams`, `param_fixes_json`, candidate and crop PNGs), `elapsed_ms`.

Frontend mirrors these types in [`react-front/src/types/debug.ts`](../../react-front/src/types/debug.ts).
