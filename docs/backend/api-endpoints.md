# API Endpoints

Image routes live in [`fastApi-app/api/routes.py`](../../fastApi-app/api/routes.py). 3D routes live in [`fastApi-app/api/model_3d.py`](../../fastApi-app/api/model_3d.py).

| Method | Path | Request | Response |
|---|---|---|---|
| `GET` | `/images/sessions` | none | `list[SessionInfo]` |
| `POST` | `/images/upload` | multipart file | `ImageUploadResponse` |
| `POST` | `/images/segment` | `SegmentRequest` | `SegmentResponse` |
| `POST` | `/images/inpaint` | `InpaintMaskRequest` | `InpaintMaskResponse` |
| `POST` | `/images/click` | `ClickRequest` | `ClickResultResponse` legacy one-step flow |
| `POST` | `/images/{uid}/name` | `SetNameRequest` | `SessionInfo` |
| `DELETE` | `/images/{uid}` | path `uid` | 204 No Content |
| `GET` | `/images/{uid}/cache` | path `uid` | `UidCacheStatusResponse` |
| `GET` | `/images/{uid}/objects` | path `uid` | `ObjectListResponse` |
| `GET` | `/images/{uid}/background` | path `uid` | PNG file |
| `GET` | `/images/{uid}/cutout` | path `uid` | latest object cutout PNG |
| `GET` | `/images/{uid}/original` | path `uid` | original image file |
| `GET` | `/images/objects/{object_uuid}` | path `object_uuid` | `ObjectMetadataResponse` |
| `PATCH` | `/images/objects/{object_uuid}` | `SetObjectNameRequest` | `ObjectMetadataResponse` |
| `POST` | `/images/objects/{object_uuid}/rescale-by-depth` | `RescaleByDepthRequest` | `RescaleByDepthResponse` |
| `POST` | `/3d/test-3d` | `{"uid":"...", "object_id": 0}` | GLB bytes |
| `GET` | `/3d/{uid}/{object_id}` | path `uid`, `object_id` | GLB file |
| `GET` | `/3d/{uid}` | path `uid` | GLB file (legacy id-0 fallback) |

## `POST /images/segment`

Runs segmentation only and returns every candidate mask as a visible BGRA cutout preview.

Behavior:

1. Validate `image_id`, natural-image `x/y`, and stored image bytes.
2. Load current canvas via `load_canvas_bytes` (progressive background if present).
3. Get or compute depth map for the canvas (`get_or_compute_depth`).
4. Delete stale temporary candidates for this `image_id`.
5. Run `ObjectSegmentor.get_mask_for_object_at_position(...)` with depth map.
6. Cache each `refined_mask` as `{uid}_mask_{mask_id}_refined.npy`.
7. Cache each cutout preview as `{uid}_mask_{mask_id}_cutout.png`.
8. Return candidate ids plus base64 cutout previews and `cutout_bounds`.

The raw refined mask is not sent to frontend. It is model input for inpainting, while the cutout is user-facing preview.

## `POST /images/inpaint`

Runs inpainting for the one mask selected by user.

Behavior:

1. Load the current canvas: `{uid}_background.png` if it exists (prior removals already applied), otherwise the original upload. This enables progressive removal — each inpaint stacks on the previous one.
2. Load selected cached `{uid}_mask_{mask_id}_refined.npy`.
3. Load matching cached `{uid}_mask_{mask_id}_cutout.png`.
4. Run `BackgroundInpainter.cut_mask_from_image(...)`.
5. Compute depth on the current canvas and derive `average_depth` over the selected mask (`build_object_metadata_for_inpaint`).
6. Allocate the next sequential `object_id` for this session (0, 1, 2 …).
7. Persist object metadata JSON (`{uid}_{object_id}_meta.json`) and register UUID in `object_index.json`.
8. Write updated canvas to `{uid}_background.png` (overwrites — becomes the new starting point for the next object).
9. Write cutout to `{uid}_{object_id}_cutout.png` (numbered — not overwritten by later inpaints).
10. Delete all temporary candidate files for that `image_id`.
11. Return `InpaintMaskResponse` with `object_id`, `object_uuid`, plus background/cutout base64.

If `mask_id` is unknown or candidate cache is gone, endpoint returns `404`.

## `GET /images/{uid}/objects`

Returns all processed objects for a session as `ObjectListResponse`. For each object id found on disk, the endpoint reads the cutout PNG, base64-encodes it, derives `cutout_bounds`, loads metadata (uuid, name, `average_depth`) when present, and checks whether a GLB model exists.

Missing individual cutouts are skipped with a WARNING log — the response is still 200 with the remaining objects. An unknown `uid` returns 200 with an empty `objects` list (same behavior as `/images/{uid}/cache`).

## `GET /images/objects/{object_uuid}`

Returns one object's persisted metadata (`ObjectMetadataResponse`): uuid, session id, object id, optional name, `average_depth`, `content_hash`, `created_at`, `has_3d`, and derived `cutout_bounds` from the on-disk cutout PNG.

Returns `404` when the UUID is absent from `object_index.json`.

## `PATCH /images/objects/{object_uuid}`

Updates the optional human-readable name on one object. Body: `SetObjectNameRequest` (`name` string or `null` to clear). Returns updated `ObjectMetadataResponse`.

## `POST /images/objects/{object_uuid}/rescale-by-depth`

Rescales a finalized cutout proportionally based on depth at a placement point. Body: `RescaleByDepthRequest` with natural-image `x`/`y`.

Behavior:

1. Load object metadata by UUID (`average_depth` is the baseline depth).
2. Load the session's current canvas and get/compute depth (`get_or_compute_depth`).
3. Sample depth at `(x, y)` (clamped to map bounds).
4. Compute `scale_factor = target_depth / average_depth` (higher uint8 depth = closer; near → far yields scale &lt; 1).
5. Scale the cutout's visible alpha content about its bbox center on a same-sized transparent canvas.
6. Overwrite `{uid}_{object_id}_cutout.png` with the rescaled PNG.
7. Update metadata `average_depth` to `target_depth` so repeated rescales do not compound.
8. Return `RescaleByDepthResponse` with pre-update `source_average_depth`, `target_depth`, `scale_factor`, and base64 cutout.

Returns `404` when object or cutout is missing; `400` when depth values are invalid or the cutout has no visible alpha.

Not wired in the React frontend today.

## `DELETE /images/{uid}`

Deletes a session and all its associated files from disk:
- Removes `uid` from `sessions.json` and `names.json`.
- Removes the original upload (`{uid}.*`), final background, all numbered cutouts (`{uid}_{oid}_cutout.png`), all numbered GLBs (`{uid}_{oid}.glb`), candidate masks, depth cache files (`{uid}_depth_*.npy`), object metadata JSON (`{uid}_{oid}_meta.json`), UUID index entries, and the click-debug overlay.
- Legacy `{uid}_cutout.png` and `{uid}.glb` are also removed for pre-numbering sessions.
- Missing files are silently ignored.

Returns 204 No Content on success.

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
