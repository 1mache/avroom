# API Endpoints

Image routes live in [`fastApi-app/api/routes.py`](../../fastApi-app/api/routes.py). 3D routes live in [`fastApi-app/api/model_3d.py`](../../fastApi-app/api/model_3d.py). Novel-view (rotation) routes live in [`fastApi-app/api/novel_view.py`](../../fastApi-app/api/novel_view.py). Debug/inspection routes live in [`fastApi-app/api/debug_vision.py`](../../fastApi-app/api/debug_vision.py) — see [Debug endpoints](#debug-endpoints).

| Method | Path | Request | Response |
|---|---|---|---|
| `GET` | `/images/sessions` | none | `list[SessionInfo]` |
| `POST` | `/images/upload` | multipart file | `ImageUploadResponse` (422 on failed technical or content validation) |
| `POST` | `/images/segment` | `SegmentRequest` | `SegmentResponse` |
| `POST` | `/images/inpaint` | `InpaintMaskRequest` | `InpaintMaskResponse` |
| `POST` | `/images/{uid}/batch` | `BatchRequest` | `BatchResponse` |
| `POST` | `/images/click` | `ClickRequest` | `ClickResultResponse` legacy one-step flow |
| `POST` | `/images/{uid}/name` | `SetNameRequest` | `SessionInfo` |
| `POST` | `/images/{uid}/sync-check` | `SessionSyncCheckRequest` | `SessionSyncCheckResponse` |
| `DELETE` | `/images/{uid}` | path `uid` | 204 No Content |
| `GET` | `/images/{uid}/cache` | path `uid` | `UidCacheStatusResponse` |
| `GET` | `/images/{uid}/objects` | path `uid` | `ObjectListResponse` |
| `GET` | `/images/{uid}/background` | path `uid` | PNG file |
| `GET` | `/images/{uid}/cutout` | path `uid` | latest object cutout PNG |
| `GET` | `/images/{uid}/original` | path `uid` | original image file |
| `GET` | `/images/{uid}/preview` | path `uid` | dashboard thumbnail JPEG (404 if none yet) |
| `POST` | `/images/{uid}/preview` | `SessionPreviewRequest` | 204 No Content |
| `GET` | `/images/objects/{object_uuid}` | path `object_uuid` | `ObjectMetadataResponse` |
| `PATCH` | `/images/objects/{object_uuid}` | `UpdateObjectRequest` | `ObjectMetadataResponse` |
| `POST` | `/images/objects/{object_uuid}/duplicate` | path `object_uuid` | `DuplicateObjectResponse` |
| `DELETE` | `/images/objects/{object_uuid}` | path `object_uuid` | 204 No Content |
| `POST` | `/images/objects/{object_uuid}/rescale-by-depth` | `RescaleByDepthRequest` | `RescaleByDepthResponse` |
| `POST` | `/images/novel-view` | `NovelViewRequest` | `NovelViewResponse` |
| `POST` | `/3d/test-3d` | `{"uid":"...", "object_id": 0}` | GLB bytes |
| `GET` | `/3d/{uid}/{object_id}` | path `uid`, `object_id` | GLB file |
| `GET` | `/3d/{uid}` | path `uid` | GLB file (legacy id-0 fallback) |
| `POST` | `/debug/validate` | multipart `file` | `DebugValidationResponse` |
| `POST` | `/debug/depth-map` | multipart `file` + query params | PNG bytes |
| `POST` | `/debug/normal-map` | multipart `file` + `hub_model` query | PNG bytes |
| `POST` | `/debug/sam-everything` | multipart `file` + query params | PNG bytes |
| `POST` | `/debug/auto-mask-pick` | multipart `file` + `x` `y` query | `DebugAutoMaskPickResponse` |
| `POST` | `/debug/inpaint-verify` | multipart `file` + `x` `y` `mask_index` query | `DebugInpaintVerifyResponse` |

## `POST /images/upload`

Accepts a multipart image file and persists it when validation passes (or when validation is disabled).

Behavior:

1. Read upload bytes from the multipart field `file`.
2. When `VALIDATE` is enabled (default), run deterministic technical checks via `ImageValidator` ([`core/image_validation/`](../../fastApi-app/core/image_validation/)): format/MIME, size, decode, resolution, blur, exposure, alpha emptiness, uniform scene. Returns **422** on failure; nothing is written to disk.
3. When `VALIDATE` is enabled, run ML content validation via `InferenceClient.run_validate_content` → `ContentImageValidator` → `ContentValidationFacade`. Returns **422** with rejection messages on failure.
4. When `VALIDATE=false`, skip steps 2–3 and persist immediately.
5. Write `{image_id}.{ext}` under the configured image storage directory.
6. Register `image_id` in `sessions.json` and bump `last_changed`.

Thresholds for technical checks are env-configurable — see [`settings.py`](../../fastApi-app/settings.py) (`UPLOAD_*` helpers). Set `VALIDATE=false` before starting the server to disable both validation stages.

## `POST /images/segment`

Runs segmentation only and returns candidate masks as visible BGRA cutout previews. Request field `verify` defaults to `manual` (all candidates). `verify=auto` still caches all six, then CLIP-picks one via `select_best_cutout`; no viable mask → **422**.

Behavior:

1. Reject with **409 Conflict** if click `(x, y)` falls inside an active inpaint region lease.
2. Validate `image_id`, natural-image `x/y`, and stored image bytes.
3. Load current canvas via `load_canvas_bytes` (progressive background if present).
4. Get or compute depth map for the canvas (`get_or_compute_depth`).
5. Delete stale temporary candidates for this `image_id`, **skipping mask ids pinned by active inpaint leases**.
6. Run `ObjectSegmentor.get_mask_for_object_at_position(...)` with depth map.
7. Cache each `refined_mask` as `{uid}_mask_{mask_id}_refined.npy` (mask ids skip pinned slots).
8. Cache each cutout preview as `{uid}_mask_{mask_id}_cutout.png`.
9. If `verify=auto`, run `select_best_cutout` and return only the winner (or **422** `no viable mask`).
10. Return candidate ids plus base64 cutout previews and `cutout_bounds`.

Segment may run while an inpaint is in flight on a non-overlapping region. See [concurrency.md](concurrency.md).

The raw refined mask is not sent to frontend. It is model input for inpainting, while the cutout is user-facing preview.

## `POST /images/inpaint`

Runs inpainting for the one mask selected by user. Request field `verify` is accepted (`manual` default) and ignored this slice.

Behavior:

1. **Admit** inpaint: load selected mask, register region lease, pin `mask_id` on disk. Returns **409** if mask overlaps an in-flight removal.
2. **Acquire canvas writer** for this session (blocks until free; **409** on timeout via `INFERENCE_JOB_TIMEOUT_SEC` unless `INFERENCE_JOB_TIMEOUT=false`).
3. Load the current canvas: `{uid}_background.png` if it exists (prior removals already applied), otherwise the original upload.
4. Load selected cached `{uid}_mask_{mask_id}_refined.npy`.
5. Load matching cached `{uid}_mask_{mask_id}_cutout.png`.
6. Run `BackgroundInpainter.cut_mask_from_image(...)`.
7. Compute depth on the current canvas and derive `average_depth` over the selected mask (`build_object_metadata_for_inpaint`).
8. Allocate the next sequential `object_id` for this session (0, 1, 2 …).
9. Persist object metadata JSON (`{uid}_{object_id}_meta.json`) and register UUID in `object_index.json`.
10. Write updated canvas to `{uid}_background.png` (overwrites — becomes the new starting point for the next object).
11. Write cutout to `{uid}_{object_id}_cutout.png` (numbered — not overwritten by later inpaints).
12. Delete **only** the selected candidate (`delete_candidate`, not all masks).
13. Drop lease and release canvas writer.
14. Bump session `last_changed` via `touch_session`.
15. Return `InpaintMaskResponse` with `object_id`, `object_uuid`, plus background/cutout base64.

If `mask_id` is unknown or candidate cache is gone, endpoint returns `404`. Overlap or canvas-busy conflicts return `409`. See [concurrency.md](concurrency.md).

## `POST /images/{uid}/batch`

Blocking `def` handler. Discovers masks (`box` via SAM-everything on adapted depth, `clicks` via `verify=auto` segment, `objects` skips inpaint), peels overlapping stacks nearer-first using exclusive-region depth, inpaints sequentially with Hybrid verification, then generates GLBs. Per-object failures are skipped. Same-batch canvas updates are not treated as 409. External overlapping leases still 409 that object (skip). `verify` is forced to `auto`.

Orchestrator: [`fastApi-app/core/batch_jobs.py`](../../fastApi-app/core/batch_jobs.py). Peel helpers: [`TestModules/src/core/batch_peel.py`](../../TestModules/src/core/batch_peel.py).

## `GET /images/{uid}/objects`

Returns all processed objects for a session as `ObjectListResponse`. For each object id found on disk, the endpoint reads the cutout PNG, base64-encodes it, derives `cutout_bounds`, loads metadata (uuid, name, `average_depth`) when present, and checks whether a GLB model exists.

Missing individual cutouts are skipped with a WARNING log — the response is still 200 with the remaining objects. An unknown `uid` returns 200 with an empty `objects` list (same behavior as `/images/{uid}/cache`).

## `GET /images/objects/{object_uuid}`

Returns one object's persisted metadata (`ObjectMetadataResponse`): uuid, session id, object id, optional name, `average_depth`, `content_hash`, `created_at`, `has_3d`, derived `cutout_bounds` from the on-disk cutout PNG, and persisted `offset_x`/`offset_y` (drag position, natural-image pixels; `(0, 0)` until the object is dragged and its offset persisted).

Returns `404` when the UUID is absent from `object_index.json`.

## `PATCH /images/objects/{object_uuid}`

Partial update for one object: name and/or drag offset. Body: `UpdateObjectRequest` — `name` (string or `null` to clear), `offset_x`/`offset_y` (floats, natural-image pixels). Returns updated `ObjectMetadataResponse`. Bumps the parent session's `last_changed` timestamp.

Each field is independently optional, and the handler distinguishes "omitted from the request" from "explicitly sent" via `request.model_fields_set` rather than relying on Pydantic defaults — necessary because `name: null` means "clear the name" while an omitted `offset_x`/`offset_y` means "leave it alone." A drag-persist call sends only `{offset_x, offset_y}`; a rename call sends only `{name}`; neither can accidentally reset the other's field. The frontend's `finishDrag` (`WorkspaceScreen.tsx`) fires this after every drag; `renameObject`/`setObjectName` fires it after a rename.

## `POST /images/objects/{object_uuid}/duplicate`

Clones one finalized object into a new object in the same session. No request body. Returns `DuplicateObjectResponse` with the new `object_uuid`.

Behavior:

1. Resolve source metadata by UUID; **404** if missing.
2. Resolve the source cutout (`{uid}_{object_id}_cutout.png`); **404** if missing.
3. Acquire the session canvas writer (no region lease — clone has no mask). **409** on writer timeout.
4. Allocate the next sequential `object_id`.
5. Build clone metadata: fresh UUID/`created_at`, copied `average_depth` / `source_elevation_deg` / `content_hash`, plus sticky lineage fields (`clone_root_uuid`, `clone_root_label`, `clone_index`), plus a nudged `offset_x`/`offset_y` (see below).
6. Nickname: first clone is `"<root>-copy"`; later clones are `"<root>-copy1"`, `"<root>-copy2"`, …. Unnamed roots use `"Object <object_id>"` as the root label. Cloning a clone (or a renamed copy) keeps the original root label/ordinal sequence.
7. Copy per-object artifacts under the writer: cutout (required), optional GLB, and any novel-view / preview PNG caches (timestamps preserved via `copy2`).
8. Persist clone metadata JSON and register the new UUID in `object_index.json`.
9. `touch_session(uid)` so sync clients refresh.
10. On failure after allocation, delete partial destination artifacts and prune any index entry; return **500**.

**Position nudge:** the clone doesn't land exactly on its source. `duplicate_object` decodes the source cutout PNG (`extract_cutout_bounds_from_png_bytes`) to get the canvas size and the object's alpha bounds, then `build_clone_metadata` / `_nudge_clone_offset` (`core/object_metadata.py`) tries shifting the clone's `offset_x` left by `max(12, bbox_width * 0.15)` pixels; if that would push it past the canvas edge, it tries the same shift right instead; if neither fits, the clone keeps the source's exact offset. `offset_y` is always copied unchanged (horizontal nudge only). This is atomic with clone creation — no separate request, no window where the clone exists un-nudged.

Does **not** rewrite `{uid}_background.png`, depth `.npy` caches, camera calib, the original upload, or temp segment masks. Depth is shared through the copied `content_hash`.

## `DELETE /images/objects/{object_uuid}`

Permanently deletes one object and every per-object artifact: the numbered cutout, GLB, all novel-view/preview caches, the metadata JSON, and the `object_index.json` UUID entry. For a legacy `object_id == 0` it also removes the unnumbered `{uid}_cutout.png` / `{uid}.glb` pair, so the object doesn't reappear (`list_object_ids` counts a present legacy cutout as id 0).

**Does not** touch anything session-scoped: the background canvas keeps the object's inpainted hole (deletion never restores original pixels), the depth cache, camera calibration, the original upload, and the dashboard preview thumbnail all survive untouched. The preview goes briefly stale — the frontend reposts it on its own debounce, and `touch_session` alone is enough to invalidate its cache-buster.

Behavior:

1. Resolve `object_uuid` via `get_object_by_uuid`; **404** if unknown. A second delete of the same uuid also 404s (idempotent-ish).
2. Acquire the session's canvas writer lock (same sandwich as `duplicate_object`); **409** on timeout. Needed because deletion changes what `list_object_ids`/`next_object_id` see, and a concurrent inpaint or duplicate could otherwise race an id allocation.
3. Delete artifacts, remove the index entry, `touch_session` — all inside the lock.
4. **500** on unexpected failure.

Plain `def`, not `async def` — it blocks on the writer lock; see `tests/test_concurrency.py`. Freeing an id makes it eligible for reuse by the next inpaint (ids are `max(existing)+1`); no id is ever reserved.

Known cosmetic edge: deleting a clone root leaves any surviving clones pointing at a dead `clone_root_uuid`, and since clone-name counting only scans survivors, a later duplicate can reuse a freed `-copy` name. Not repaired — no lineage cleanup runs on delete.

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
9. Bump the parent session's `last_changed` timestamp.

Returns `404` when object or cutout is missing; `400` when depth values are invalid or the cutout has no visible alpha.

Not wired in the React frontend today.

## `POST /images/novel-view`

Synthesizes a 2D novel view of an existing object cutout at a requested camera pose (rotation UI). Body: `NovelViewRequest`; see [novel-view contracts](../ai-pipeline/ai-engines/novel-view/contracts.md) for the full field table and sign conventions. Full model/pipeline documentation lives under [`docs/ai-pipeline/ai-engines/novel-view/`](../ai-pipeline/ai-engines/novel-view/); this section only covers the HTTP-layer behavior added on top.

Behavior:

1. Resolve signed pose via `NovelViewRotationAdapter.resolve_pose(...)` (direction-enum handling; **422** on an invalid pose).
2. **Snap** the resolved azimuth and relative elevation to the nearest 10° (`ROTATION_STEP_DEG` in `novel_view.py`) and wrap azimuth into `(-180, 180]`. This is an HTTP-only concern — the adapter and direct Python API are untouched and keep accepting exact angles. Radius is never snapped (it's a distance, not an angle).
3. **404** if the object's cutout (`{uid}_{object_id}_cutout.png`) doesn't exist yet.
4. Check the disk cache at `object_novel_view_path(uid, object_id, snapped_azimuth, snapped_elevation)`. A cache hit requires the cached file's mtime to be `>=` the cutout's mtime — `rescale-by-depth` rewrites the cutout in place, so an older cached rotation is treated as stale and re-synthesized rather than served.
5. On a cache hit: read cached PNG bytes, skip inference, **skip `touch_session`** (nothing changed).
6. On a cache miss: run inference (`JobKind.NOVEL_VIEW`, seed fixed at 0 — deterministic given the same cutout + pose), write the PNG to the cache path, and `touch_session(uid)`.
7. Return `NovelViewResponse` with the **snapped** azimuth/elevation echoed back (not the raw request values), so the client learns the pose that was actually rendered.

Does **not** take a canvas-writer lock or region lease, and never mutates the cutout PNG or session objects — a rotation request can run concurrently with anything else and always starts from the same pristine cutout, which is what makes "rotate again" restart cleanly from the default pose.

## `DELETE /images/{uid}`

Deletes a session and all its associated files from disk:
- Removes `uid` from `sessions.json`, `names.json`, and `session_timestamps.json`.
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
3. On success, write `{uid: name}` entry to `tmp/names.json`, bump `last_changed`, and return `SessionInfo`.

Names are unique across all sessions. Renaming a uid to its current name is a no-op (allowed).

## `POST /images/{uid}/sync-check`

Compares a client-held session timestamp against server truth so the frontend can detect stale local state.

Body: `SessionSyncCheckRequest` with `client_last_changed` (ISO-8601 UTC string the client believes is current, or `null` when unknown).

Behavior:

1. Return **404** when `uid` is absent from `sessions.json`.
2. Read server truth from `session_timestamps.json` via `get_session_last_changed`. Legacy sessions with no recorded timestamp use an empty string.
3. Set `needs_refresh = (client_last_changed != server_last_changed)`.
4. Always return the current server `last_changed` so the client can correct its local copy.

Returns `SessionSyncCheckResponse` with `last_changed` and `needs_refresh`.

## Session dirty timestamps

Client-visible durable mutations bump `last_changed` through `touch_session` in [`settings.py`](../../fastApi-app/settings.py):

| Endpoint | Module |
|---|---|
| `POST /images/upload` | `api/routes.py` |
| `POST /images/click` | `api/routes.py` |
| `POST /images/inpaint` | `api/routes.py` |
| `POST /images/{uid}/name` | `api/routes.py` |
| `PATCH /images/objects/{object_uuid}` | `api/routes.py` |
| `POST /images/objects/{object_uuid}/duplicate` | `api/routes.py` |
| `DELETE /images/objects/{object_uuid}` | `api/routes.py` |
| `POST /images/objects/{object_uuid}/rescale-by-depth` | `api/routes.py` |
| `POST /3d/test-3d` | `api/model_3d.py` |
| `POST /images/novel-view` (cache miss only — a cache hit changes nothing and skips the touch) | `api/novel_view.py` |

These do **not** bump session dirty state: `POST /images/segment` candidate caches, depth `.npy` cache writes, in-memory region leases.

## `GET /images/sessions`

Returns all registered UIDs enriched with human-readable names from `names.json` and each session's `last_changed` timestamp when recorded. Uids without a saved name have `name: null`.

## `GET /images/{uid}/preview` and `POST /images/{uid}/preview`

Dashboard thumbnail for one session — the room roughly as the user left it, so cards on the dashboard are recognizable rather than name-only.

- **`GET`** serves `{uid}_preview.jpg`. Returns **404** when the file doesn't exist yet; the dashboard card falls back to a placeholder rather than treating this as an error. Callers add a `?t=<last_changed>` query param purely as a browser cache-buster — the server ignores it.
- **`POST`** stores a client-composited thumbnail. Body: `SessionPreviewRequest` (`image_b64`, base64 JPEG, no `data:` prefix).
  1. **404** if `uid` isn't registered in `sessions.json`.
  2. **422** if `image_b64` isn't valid base64, or if the decoded bytes don't open as an image (`PIL.Image.verify()`).
  3. Written atomically (temp file + `os.replace`) to `{uid}_preview.jpg`.
  4. **Does not** call `touch_session` — the frontend fires this 500ms after the mutation that already bumped `last_changed` (`PREVIEW_DEBOUNCE_MS` in `WorkspaceScreen.tsx`'s debounced capture), so the cache-buster the dashboard reads is already correct.

**`POST /images/upload`** also writes an initial thumbnail — a downscaled copy of the original upload via `core/session_preview.py::write_upload_preview` — so a session has a preview from the moment it's created, before any edit. Failure here is logged and swallowed (non-fatal, same shape as camera calibration), never fails the upload.

`DELETE /images/{uid}` removes `{uid}_preview.jpg` along with the rest of the session's artifacts.

## `GET /images/{uid}/cache`

Returns final artifact existence flags, derives `cutout_bounds` from cached final cutout PNG when present, and includes the saved `name` from `names.json`. Session restore uses this to recover drag bounds and display the session label without re-running segmentation.

## Bounds Extraction

`_extract_cutout_bounds_from_png_bytes(...)` decodes PNG with alpha, finds non-zero alpha pixels, and returns tight visible-object bounds. If decode or alpha is missing, it falls back to full-image bounds where possible.

## Debug endpoints

Router: [`fastApi-app/api/debug_vision.py`](../../fastApi-app/api/debug_vision.py), prefix `/debug`. Pipeline functions: [`fastApi-app/core/debug_vision.py`](../../fastApi-app/core/debug_vision.py). Test/inspection tools, not part of the production object-removal flow — **no session is created, nothing is written to disk**. All of them are gated by `DEBUG_ENDPOINTS` (`settings.get_debug_endpoints_enabled()`, default enabled); when disabled, they return **404**. Frontend entry point: the dashboard header's flask icon opens `DebugScreen` (see [frontend/user-flow.md](../frontend/user-flow.md#pipeline-debug-screen)).

GPU jobs dispatch through the inference pool (`JobKind.DEBUG_DEPTH_MAP` / `DEBUG_NORMAL_MAP` / `DEBUG_SAM_EVERYTHING` / `DEBUG_AUTO_MASK_PICK` / `DEBUG_INPAINT_VERIFY`; `/debug/validate`'s content stage reuses `JobKind.VALIDATE_CONTENT`). Those debug job kinds are in `_FACADE_JOB_KINDS` (`core/inference_pool/dispatch.py`) so inline mode takes the GPU lock. JSON debug jobs put their payload on `JobResult.debug_payload`.

### `POST /debug/validate`

Runs the **full** upload-validation scoreboard on an image, with no side effects. Unlike `POST /images/upload`, this never persists anything, never creates a session, and never stops at the first failed check — every technical check plus the content (CLIP) checks all run and are reported regardless of pass/fail. Always returns **200**; a failed check is data, not an error. Runs independently of the `VALIDATE` env var (this endpoint *is* the validator).

1. Technical stage: `ImageValidator().validate_all(...)` (`core/image_validation/validator.py`) — every check runs even after an earlier one fails, unlike `validate()` (used by `POST /images/upload`), which raises `ImageValidationError` on the first failure. Both share one private `_run_checks(..., stop_on_first_failure: bool)` runner.
2. A `decode` failure is still terminal for the technical stage (every check past `format_mime` reads from the decoded context) — reported as one failed `decode` check, and the content stage is skipped (`content_skipped_reason` set).
3. Content stage (skipped only on decode failure): `get_inference_client().run_validate_content(...)` — the same `JobKind.VALIDATE_CONTENT` job `POST /images/upload` uses.
4. Response `ok = technical_ok and (content_ok is not False)`.

See `DebugValidationResponse` in [schemas.md](schemas.md#debug).

### `POST /debug/depth-map`

Renders a depth map for an uploaded image as a viewable PNG (not a `.npy` array). Query params:

| Param | Default | Notes |
|---|---|---|
| `model` | `LiheYoung/depth-anything-small-hf` | HF checkpoint name. Only used when `strategy=anything`. |
| `colormap` | `none` | One of `none`, `inferno`, `magma`, `turbo`, `jet`. `none` renders grayscale. |
| `strategy` | `anything` | One of `anything`, `blended`, `enhanced_edge` — see below. |

`core/debug_vision.py::_build_depth_strategy(strategy, model_name)` selects the depth-mapping strategy:

- `anything` — `DepthAnythingMappingStrategy(model_name)`, a single checkpoint; the only one of the three that honors `model`.
- `blended` — `NearFarBlendedDepthMappingStrategy()`, the near+far alpha-blended composite production actually feeds into edge enhancement (see [AI Pipeline Architecture](../../CLAUDE.md#ai-pipeline-architecture-critical)).
- `enhanced_edge` — `EnhancedEdgeDepthMappingStrategy()`, `blended` plus CLAHE + bilateral filtering — production's **true default** (`DepthMappingFacade`'s own default strategy).

Response is `image/png` with header `X-Elapsed-Ms`. `422` on an unknown `colormap`/`strategy` or an undecodable upload.

### `POST /debug/normal-map`

Renders a Metric3D surface-normal map as a viewable PNG (`(n+1)/2` RGB encoding via `colorize_normals`). Query params:

| Param | Default | Notes |
|---|---|---|
| `hub_model` | `metric3d_vit_small` | One of `metric3d_vit_small`, `metric3d_vit_large`, `metric3d_vit_giant2` (ViT hubs only — ConvNeXt has no normals). |

Dispatches `JobKind.DEBUG_NORMAL_MAP` through the inference pool. Response is `image/png` with header `X-Elapsed-Ms`. `422` on an unknown `hub_model` or an undecodable upload. The DebugScreen samples nx/ny/nz from the displayed PNG on click (8-bit quantization).

### `POST /debug/sam-everything`

Renders SAM's `SamAutomaticMaskGenerator` ("segment everything", prompt-free) output as a colored overlay on the original photo. Query params:

| Param | Default | Notes |
|---|---|---|
| `source` | `depth` | `depth` feeds SAM the adapted depth map (production's rule — see [AI Pipeline Architecture](../../CLAUDE.md#ai-pipeline-architecture-critical)); `rgb` feeds the raw photo instead, to demonstrate why that rule exists (visibly more/noisier masks from fabric creases and shadows). |
| `depth_strategy` | `anything` | Only used when `source=depth`. Same three options as `/debug/depth-map`'s `strategy`. |
| `depth_model` | `LiheYoung/depth-anything-small-hf` | Only used when `source=depth` and `depth_strategy=anything`. |
| `points_per_side` | `16` | SAM probe grid density, `4`–`64`. Runtime scales with the square of this value (`points_per_side²` forward passes). |
| `pred_iou_thresh` | `0.88` | `0.0`–`1.0`. Minimum predicted mask-quality IoU to keep a candidate — matches `SamAutomaticMaskGenerator`'s own default. |
| `stability_score_thresh` | `0.95` | `0.0`–`1.0`. Minimum stability score (robustness under threshold perturbation) to keep a candidate. |
| `min_mask_region_area` | `0` | `0`–`100000`. Discards connected components smaller than this many pixels (`cv2.connectedComponents`-based post-processing inside `segment_anything`, no pycocotools dependency). |
| `alpha` | `0.45` | `0.0`–`1.0`. Overlay tint strength. |

The overlay is **always** drawn on the original photo, regardless of `source`. Response is `image/png` with headers `X-Mask-Count` and `X-Elapsed-Ms` — both must be read via `expose_headers` on the CORS middleware (see [settings-and-storage.md](settings-and-storage.md)) for browser JS to see them. `422` on an unknown `source`/`depth_strategy` or an undecodable upload.

Underlying capability: `SamSegmentationStrategy.predict_everything(image, *, points_per_side, pred_iou_thresh, stability_score_thresh, min_mask_region_area)` in [`TestModules/src/ai_engines/segmentation/strategies/sam_segmentation_strategy.py`](../../TestModules/src/ai_engines/segmentation/strategies/sam_segmentation_strategy.py) — a non-abstract method on `ImageSegmentationStrategy` (default raises `NotImplementedError`, since prompt-free segmentation is SAM-specific) exposed at the facade level as `ImageSegmentationFacade.get_all_masks_for_image(...)`. Reuses the already-loaded `SamPredictor`'s weights via `_load_sam_mask_generator` (`functools.lru_cache`, keyed on checkpoint + all four threshold args) — no duplicate 370MB checkpoint load. Rendering uses `avroom_object_removal.utils.overlay_masks` (deterministic per-mask color via golden-ratio hue stepping, translucent fill + outline).

### `POST /debug/auto-mask-pick`

Runs `ObjectSegmentor` at query `x`,`y` (natural-image pixels) then `select_best_cutout`. Returns every candidate's preview/cutout PNG (base64), CLIP crop when scored, `score`, `reason`, and `winner_index`. Does **not** write session mask cache. `422` if the click is outside the image.

### `POST /debug/inpaint-verify`

Same click segmentation as auto-mask-pick, then hybrid inpaint on `mask_index` (optional; defaults to CLIP winner). Returns LaMa PNG, per-retry candidate + CLIP crop, CLIP scores, SD params sent, verifier `param_fixes_json`, and the final sharpened image. `422` if the click is out of bounds, `mask_index` is out of range, or there is no viable mask when `mask_index` is omitted.
