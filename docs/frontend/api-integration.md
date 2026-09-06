# API Integration

All backend traffic goes through [`react-front/src/api/images.ts`](../../react-front/src/api/images.ts). It uses native `fetch`.

## Base URL

`API_BASE_URL` reads `VITE_API_BASE_URL` or falls back to `http://127.0.0.1:8000`.

## Helpers

`handleJsonResponse<T>(...)` throws a typed `ApiError` (with `.status` and `.detail` parsed from FastAPI's `{"detail": ...}` envelope) on non-2xx responses, so callers can distinguish an expected 409 from a real failure by status code rather than string-matching the message. `WorkspaceScreen`/`DashboardScreen` show `.detail` in the generic error modal unless `useConflictNotices` intercepts a 409 first (see [state-and-types.md](state-and-types.md)).

## Upload

`uploadImage(file)` posts multipart form data to `POST /images/upload` and returns `ImageUploadResponse`.

## Segmentation

`segmentImage(payload)` posts JSON to `POST /images/segment`.

Payload:

```ts
{ image_id: string; x: number; y: number; options?: ClickRequestOptions }
```

Response contains `masks[]`; each mask has:

- `mask_id` for later inpainting.
- `cutout_b64` preview rendered in modal.
- `format`, currently `png`.
- `cutout_bounds` for future final cutout drag behavior.

## Inpainting

`inpaintMask({ image_id, mask_id })` posts JSON to `POST /images/inpaint`.

Response is `InpaintMaskResponse`, which extends `ClickResultResponse` and adds `object_id` and `object_uuid`:

```ts
{
  image_id: string;
  background_b64: string;
  cutout_b64: string;
  format: string;
  cutout_bounds?: CutoutBounds | null;
  object_id: number;
  object_uuid: string;
  source_elevation_deg?: number;
}
```

`WorkspaceScreen` turns base64 strings into `data:image/png;base64,...` URLs for the background and cutout `<img>` elements.

## Sessions

`getSessions()` fetches `GET /images/sessions` and returns `SessionInfo[]`. Each entry has `uid` and `name` (nullable). Previously returned bare `string[]`; updated after session naming was added.

`setSessionName(uid, name)` posts `{name}` to `POST /images/{uid}/name` and returns the updated `SessionInfo`. Backend enforces uniqueness — on collision the backend returns 409 and `handleJsonResponse` throws an `ApiError`, which `WorkspaceScreen` routes to the generic error modal (not `useConflictNotices` — a duplicate name is a real conflict, not expected region-lease traffic).

### Dashboard preview thumbnails

`sessionPreviewUrl(uid, lastChanged)` builds a `GET /images/{uid}/preview` URL with `lastChanged` as a `?t=` cache-buster; `SessionCard` renders it directly as an `<img src>` and falls back to a placeholder on `onError` (404 when no preview exists yet).

`saveSessionPreview(uid, imageB64)` posts `{ image_b64 }` to `POST /images/{uid}/preview`, best-effort (caller swallows failures). `PREVIEW_API_READY` in `api/images.ts` gates this call (currently `true`, a no-op early return if flipped `false`) — `sessionPreviewUrl` itself is unconditional.

`WorkspaceScreen` composites the thumbnail client-side (`utils/preview.ts::composeSessionPreview` — background plus every visible cutout at its current offset, drawn onto an offscreen canvas, downscaled to 640px, JPEG q0.82) and calls `saveSessionPreview` debounced 500ms (`PREVIEW_DEBOUNCE_MS`) after any mutation settles: inpaint, novel-view result, rename, duplicate, drag-end, delete, and hide/show toggles. The backend also writes an initial thumbnail at upload time (a downscaled copy of the original), so a session never shows an empty placeholder once uploaded.

`preview.ts::loadForCanvas` fetches images with `cache: "reload"` rather than the more obvious `<img crossOrigin="anonymous">` approach — the stage's own plain `<img src={photoSrc}>` (no `crossOrigin`) loads that same, cache-busted background URL moments before every capture (via `useSessionSync`'s `?t=<lastChanged>` reconcile), and the browser's HTTP cache can hand a `cors`-mode fetch the opaque no-cors response from that `<img>` load, which then fails CORS even though the server's real response carries proper headers. Forcing a fresh network round-trip sidesteps the collision. Confirmed via browser devtools; without this the client-composited preview silently never updates after the first upload-time thumbnail.

## Objects

`getSessionObjects(uid)` fetches `GET /images/${uid}/objects` and returns `ObjectListResponse`. Used by `WorkspaceScreen` (via `useSessionJobs.loadRestoredObjects`) on session restore to populate the full `objects[]` array, and by `useSessionSync`'s reconcile, and by `useSessionJobs.duplicateObject` to fetch a freshly-cloned object's metadata. Each `ObjectInfo` may include `uuid`, `name`, and `average_depth` when metadata was persisted at inpaint time.

`setObjectName(objectUuid, name)` sends `PATCH /images/objects/${objectUuid}` with `{ name }`.

`setObjectOffset(objectUuid, x, y)` sends `PATCH /images/objects/${objectUuid}` with `{ offset_x, offset_y }` — note it never includes `name`, so the backend's partial-update handling leaves the object's name untouched (see `UpdateObjectRequest` in [schemas.md](../backend/schemas.md)). `WorkspaceScreen`'s `finishDrag` fires this once per drag (not per pointermove) so the position survives a session close/reopen; `loadRestoredObjects` (`useSessionJobs.ts`) reads `offset_x`/`offset_y` back off `ObjectInfo` on restore instead of resetting to `(0, 0)`. Failure is `console.warn`-logged, not surfaced to the user — a missed save on one drag just gets overwritten by the next.

Duplicating an object no longer copies the source's exact `offset` client-side; the clone's nudged position is computed server-side (`build_clone_metadata`, atomic with clone creation — see [api-endpoints.md](../backend/api-endpoints.md#post-imagesobjectsobject_uuidduplicate)) and arrives via the `getSessionObjects` fetch `duplicateObject` already performs after cloning.

`smartPasteObject(objectUuid, x, y)` sends `POST /images/objects/${objectUuid}/smart-paste` with `{ x, y }`. When the workspace toolbar **Smart paste** switch is on, `WorkspaceScreen`'s `finishDrag` fires this after `setObjectOffset`, sampling depth at the center of the dragged object's scaled alpha bbox plus its offset (`getObjectPlacementCenter` with `effectiveDisplayBounds`). On success, `useSessionJobs.applySmartPasteResult` updates local `displayScale` from `display_scale` and clears any stale rotation preview — the cutout PNG src is unchanged.

`POST /images/objects/{uuid}/rescale-by-depth` remains a lower-level backend endpoint with no frontend wrapper.

`deleteObject(objectUuid)` calls `DELETE /images/objects/${objectUuid}`, void-returning like `deleteSession`. `useSessionJobs.deleteObject` wraps it with a busy flag (`isDeleting`) and a `uuid` guard (objects from pre-UUID sessions can't be deleted, same precondition as duplicate). The Toolbar's trash button arms a `ConfirmDialog` in `WorkspaceScreen` rather than deleting directly — deletion is permanent and the background keeps the object's inpainted hole, it's never repainted. `deletedObjectIdsRef` in `useSessionJobs` is a *pending* set now, not permanent: an id is held only while its DELETE is in flight (so a racing sync-check reconcile can't resurrect the object mid-request), then dropped once the request settles — server truth takes over, so a later object reusing the freed `object_id` isn't hidden.

## 3D

`generate3DModel(uid, objectId)` posts to `POST /3d/test-3d` with body `{ uid, object_id: objectId }`. Returns raw GLB `ArrayBuffer`.

`fetchCached3DModel(uid, objectId)` fetches `GET /3d/${uid}/${objectId}` and returns `null` on 404 (model not yet generated for that object).

## Session management

`getUidCacheStatus(uid)` fetches `GET /images/${uid}/cache` for session restore.

`warmSessionMaps(uid)` posts to `POST /images/${uid}/warm-maps` with no body. `WorkspaceScreen` fires it fire-and-forget when a session mounts and again when the user turns **Smart paste** on, so depth/normal caches are warm before the first drag-rescale; failures are `console.warn`-logged and non-fatal.

`deleteSession(uid)` calls `DELETE /images/${uid}` (no body). Throws on non-2xx.

## Legacy

`POST /images/click` still exists on the backend as a one-step legacy endpoint (see [backend/api-endpoints.md](../backend/api-endpoints.md)), but `api/images.ts` no longer has a wrapper for it — normal UI flow is `segmentImage(...)` followed by `inpaintMask(...)`.

## Debug endpoints

[`react-front/src/api/debug.ts`](../../react-front/src/api/debug.ts) — kept separate from `api/images.ts` since nothing here is session-scoped; it backs `DebugScreen` only (see [components.md](components.md#debugscreen) and [user-flow.md](user-flow.md#pipeline-debug-screen)). Re-exports/reuses `API_BASE_URL` and `ApiError` from `api/images.ts` rather than duplicating either.

- `validateImageDebug(file)` posts multipart `file` to `POST /debug/validate`, returns `DebugValidationResponse` JSON directly.
- `debugDepthMap(file, options)`, `debugNormalMap(file, options)`, and `debugSamEverything(file, options)` post multipart `file` with knobs in the query string to `POST /debug/depth-map` / `/debug/normal-map` / `/debug/sam-everything`, and return a `DebugImageResult` blob URL.
- `debugAutoMaskPick(file, seeds)` posts to `POST /debug/auto-mask-pick?x=&y=` with optional repeated `points=x,y` for seeds after the first (cap 8) and returns `DebugAutoMaskPickResponse` JSON.
- `debugInpaintVerify(file, seeds, maskIndex)` posts to `POST /debug/inpaint-verify` the same way (`mask_index` omitted when `maskIndex` is null) and returns `DebugInpaintVerifyResponse` JSON.
- Callers own the returned `objectUrl` and must `URL.revokeObjectURL(...)` it — `debug.ts` never revokes on its own. `DebugScreen` revokes the previous URL before committing a re-run's result and revokes every URL it has ever held on unmount.
- A non-OK response throws the same `ApiError` shape as `api/images.ts` (status + `detail` parsed from the FastAPI error envelope), so a `404` (from `DEBUG_ENDPOINTS=false`) can be told apart from a real failure and shown as its own message.
