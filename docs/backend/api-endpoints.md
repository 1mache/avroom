# API Endpoints

Image routes live in [`fastApi-app/api/routes.py`](../../fastApi-app/api/routes.py). Object routes live in [`fastApi-app/api/objects.py`](../../fastApi-app/api/objects.py).

| Method | Path | Request | Response |
|---|---|---|---|
| `GET` | `/images/sessions` | none | `list[SessionInfo]` |
| `POST` | `/images/upload` | multipart file | `ImageUploadResponse` |
| `POST` | `/images/segment` | `SegmentRequest` | `SegmentResponse` |
| `POST` | `/images/inpaint` | `InpaintMaskRequest` | `InpaintMaskResponse` |
| `POST` | `/images/click` | `ClickRequest` | `ClickResultResponse` legacy one-step flow |
| `POST` | `/images/{uid}/name` | `SetNameRequest` | `SessionInfo` |
| `GET` | `/images/{uid}/cache` | path `uid` | `UidCacheStatusResponse` |
| `GET` | `/images/{uid}/background` | path `uid` | PNG file |
| `GET` | `/images/{uid}/cutout` | path `uid` | PNG file |
| `GET` | `/images/{uid}/original` | path `uid` | original image file |
| `POST` | `/objects/test-3d` | `{"uid":"..."}` | GLB bytes |
| `GET` | `/objects/{uid}` | path `uid` | GLB file |

## `POST /images/segment`

Runs segmentation only and returns every candidate mask as a visible BGRA cutout preview.

Behavior:

1. Validate `image_id`, natural-image `x/y`, and stored image bytes.
2. Delete stale temporary candidates for this `image_id`.
3. Run `ObjectSegmentor.get_mask_for_object_at_position(...)`.
4. Cache each `refined_mask` as `{uid}_mask_{mask_id}_refined.npy`.
5. Cache each cutout preview as `{uid}_mask_{mask_id}_cutout.png`.
6. Return candidate ids plus base64 cutout previews and `cutout_bounds`.

The raw refined mask is not sent to frontend. It is model input for inpainting, while the cutout is user-facing preview.

## `POST /images/inpaint`

Runs inpainting for the one mask selected by user.

Behavior:

1. Load original uploaded image.
2. Load selected cached `{uid}_mask_{mask_id}_refined.npy`.
3. Load matching cached `{uid}_mask_{mask_id}_cutout.png`.
4. Run `BackgroundInpainter.cut_mask_from_image(...)`.
5. Promote result to final `{uid}_background.png` and `{uid}_cutout.png`.
6. Delete all temporary candidate files for that `image_id`.
7. Return same final response fields as legacy click flow.

If `mask_id` is unknown or candidate cache is gone, endpoint returns `404`.

## `POST /images/click`

Legacy one-step endpoint. It still runs old `ObjectRemover` pipeline and returns final background/cutout directly. Frontend no longer uses it for normal flow.

## `POST /images/{uid}/name`

Assigns a human-readable label to a session.

Behavior:

1. Call `set_session_name(uid, name)` in `settings.py`.
2. If `name` already belongs to a different uid, raise `409 Conflict` with error text.
3. On success, write `{uid: name}` entry to `tmp/names.json` and return `SessionInfo`.

Names are unique across all sessions. Renaming a uid to its current name is a no-op (allowed).

## `GET /images/sessions`

Returns all registered UIDs enriched with human-readable names from `names.json`. Uids without a saved name have `name: null`.

## `GET /images/{uid}/cache`

Returns final artifact existence flags, derives `cutout_bounds` from cached final cutout PNG when present, and includes the saved `name` from `names.json`. Session restore uses this to recover drag bounds and display the session label without re-running segmentation.

## Bounds Extraction

`_extract_cutout_bounds_from_png_bytes(...)` decodes PNG with alpha, finds non-zero alpha pixels, and returns tight visible-object bounds. If decode or alpha is missing, it falls back to full-image bounds where possible.
