# State and Types

Session-level state is split across three hooks under [`react-front/src/hooks/`](../../react-front/src/hooks/), all composed by [`WorkspaceScreen`](../../react-front/src/components/layout/WorkspaceScreen.tsx). `WorkspaceScreen` itself still owns UI-only state directly (tool modes, drag state, dialog visibility) — see [components.md](components.md).

## `useSessionJobs`

[`react-front/src/hooks/useSessionJobs.ts`](../../react-front/src/hooks/useSessionJobs.ts)

```ts
function useSessionJobs(imageId: string | null, options: UseSessionJobsOptions)
```

`UseSessionJobsOptions`: `{ onError: (error: unknown, context: JobErrorContext) => void; onMutated?: () => void }`. `JobErrorContext = "segment" | "inpaint" | "rotate" | "generic"`.

Owns `objects: CutoutObject[]`, `selectedObjectId: number | null`, `pendingJobs: PendingInpaintJob[]`, `segmentState: SegmentPickerState`, `backgroundSrc: string | null`, `isDuplicating`, `isDeleting`. Internally tracks `imageIdRef` (mirrors the `imageId` prop, for staleness checks), `objectsRef` (mirrors `objects`), `highestCommittedObjectIdRef` (starts at `-1`, monotonically forward), and `deletedObjectIdsRef: Set<number>`.

Exposed methods:

- **`runSegment(x, y, verify="manual", normalizedClickPos=null)`** — single-flight: sets `segmentState = {status:"loading"}`, calls `segmentImage` with `verify`. On `manual` success sets `{status:"choosing", maskOptions}`. On `auto` success with one mask, calls `selectMask` immediately (no picker). Drops the response if `imageIdRef.current` no longer matches (user switched sessions mid-request).
- **`selectMask(maskId, normalizedClickPos, verify="manual")`** — closes the mask picker **immediately**, generates a client-side `jobId` (module-level counter, since `object_id` doesn't exist until the response lands) and pushes a `PendingInpaintJob { jobId, maskId, normalizedClickPos, startedAt }`, then fires `inpaintMask(...)` **detached** (same `verify`) — the caller is free to click a new point and start another segment/inpaint before this one resolves. On resolve, the pending job is removed, the new `CutoutObject` is upserted into `objects` and auto-selected, and `backgroundSrc` is only overwritten if `result.object_id > highestCommittedObjectIdRef.current` (this guards against an out-of-order *network* delivery of two concurrent inpaints stomping a newer background with an older one — the backend's canvas-writer lock already makes `object_id` a valid commit order server-side).
- **`toggleHidden(objectId)`** — flips `hidden`; clears selection if the hidden object was selected.
- **`updateOffset(objectId, offset)`** — pure local `setState`, no network call. Persistence happens separately, from `WorkspaceScreen.finishDrag` via `setObjectOffset(uuid, x, y)` at drag-end.
- **`commitRotation(objectId, pose, previewSrc)`** — sets `rotation = { pose, previewSrc, src: null, bounds: null, status: "pending" }` immediately (this *is* the pending-state marker; no separate job-list entry needed). Fires `cacheNovelViewPreview(...)` detached and best-effort (swallowed), then `synthesizeNovelView(...)` detached; on success replaces `rotation` with `status: "ready"` plus the server's `src`/`bounds`; on failure sets `status: "error"`.
- **`renameObject(objectId, uuid, name)`** — awaits `setObjectName(uuid, name)`, updates the local `name`.
- **`duplicateObject(objectId)`** — awaits `duplicateObjectRequest(uuid)` for the new uuid, then re-fetches the whole session via `getSessionObjects` to get the clone's full metadata (the duplicate endpoint only returns the uuid), builds the new `CutoutObject` reusing the source's `glbData` (the server copies the GLB file) and the server-computed nudged offset, upserts and selects it.
- **`deleteObject(objectId)`** — bails if already `isDeleting`, if there's no `currentImageId`, or if the target has no `uuid` (pre-UUID legacy objects can't be deleted). Adds the id to `deletedObjectIdsRef` **before** awaiting the DELETE call, so a `useSessionSync` reconcile landing mid-flight can't resurrect the object; sets `isDeleting = true`; on success removes the object from `objects` and clears selection if needed; calls `onError(err, "generic")` on failure. In `finally`, removes the id from `deletedObjectIdsRef` and resets `isDeleting` — server truth takes back over once the request settles, so a later object reusing the freed id isn't hidden.
- **`loadRestoredObjects(restored: ObjectInfo[])`** — maps server `ObjectInfo[]` to local `CutoutObject[]` on session restore (offsets from `offset_x`/`offset_y`, `hidden` always reset `false`, `rotation`/`glbData` always `null`), and seeds `highestCommittedObjectIdRef` to the max id seen.
- **`resetSession()`** / **`isObjectDeleted(objectId)`** — full-state reset and a `deletedObjectIdsRef` read, respectively.
- **`toCutoutAlphaBounds(...)`** — also exported at module level (imported by `useSessionSync`); converts a snake_case `CutoutBounds` DTO into the camelCase `CutoutAlphaBounds` view model, or `null`.

Concurrency guards used throughout: every async `.then`/`.catch` checks `imageIdRef.current !== currentImageId` and drops the result if the session changed mid-flight; every `setObjects`/`setPendingJobs`/`setSelectedObjectId` call uses the functional updater form since multiple promises can resolve concurrently; an `upsertObject` helper reconciles "sync already pulled this object down" against "the request that created it just returned," preserving local-only `offset`/`hidden`/`glbData`.

## `useSessionSync`

[`react-front/src/hooks/useSessionSync.ts`](../../react-front/src/hooks/useSessionSync.ts)

```ts
function useSessionSync(options: UseSessionSyncOptions)
```

`UseSessionSyncOptions`: `imageId`, `hasPendingWork: boolean`, `objects`, `setObjects`, `selectedObjectId`, `setSelectedObjectId`, `setBackgroundSrc`, `isDeleted: (objectId: number) => boolean`. Returns `{ lastChanged, seedLastChanged, recordLocalMutation }`.

`POLL_INTERVAL_MS = 2000`. Polling (`setInterval(checkNow, 2000)`) runs only while `imageId` is set **and** `hasPendingWork` is true — idle sessions never poll. Independently of that, `checkNow` also fires once on the `window` `"focus"` event and on `document`'s `"visibilitychange"` event (gated on `document.visibilityState === "visible"`).

`checkNow` calls `syncCheckSession(uid, lastChangedRef.current)`; if the server reports `needs_refresh`, it awaits `reconcile`. `reconcile` fetches `getSessionObjects` + `getUidCacheStatus` in parallel, filters out client-deleted objects (`isDeleted`), and **merges** server `ObjectInfo[]` into local `CutoutObject[]` by `objectId` — for objects that already exist locally it only overwrites the server-owned fields (`uuid`, `name`, `cutoutSrc`, `cutoutAlphaBounds`, `sourceElevationDeg`), leaving `offset`/`hidden`/`glbData`/`rotation` untouched; new server objects get local defaults; objects no longer present server-side are dropped (clearing selection if selected). The background URL gets a `?t=<lastChanged>` cache-busting suffix on reconcile. Both `checkNow` and `reconcile` swallow errors — the next poll or focus tick just tries again.

`recordLocalMutation` (an alias for `checkNow`) is called by `WorkspaceScreen` after every local mutation and once after session boot, to seed `lastChanged` early — since the client's prior timestamp is stale by definition right after a local write, this always triggers one redundant-but-harmless reconcile of the state that was just produced locally.

## `useConflictNotices`

[`react-front/src/hooks/useConflictNotices.ts`](../../react-front/src/hooks/useConflictNotices.ts)

```ts
function useConflictNotices(): { notices: ConflictNotice[]; notify; dismiss }
```

`NOTICE_TTL_MS = 6000`. `ConflictContext = "segment" | "inpaint"`. `notify(error, context)` rethrows immediately if `error` is not an `ApiError` with `status === 409` — everything else falls through to the caller's own `try/catch` and the generic error modal. For an actual 409, it builds a human message (segment always gets a fixed "that area is being removed right now" message; inpaint branches on whether the detail text mentions a writer-busy timeout vs. a region overlap) and pushes a dismissible notice that auto-expires after 6 seconds. `setSessionName`'s 409 (duplicate session name) is a different, real conflict and is never routed through this hook.

## `utils/stageGeometry.ts`

[`react-front/src/utils/stageGeometry.ts`](../../react-front/src/utils/stageGeometry.ts)

| Export | Purpose |
|---|---|
| `getContainedImageRect(containerSize, imageSize)` | Reproduces `object-fit: contain` placement so overlays line up with the visible image, not the outer box. |
| `loadImageElement(src)` | Wraps `new Image()` loading in a Promise. |
| `compositePreviewOntoCanvas(snapshotDataUrl, bounds, canvasSize)` | Pastes a 3D-viewer snapshot onto a full-canvas transparent PNG at the object's alpha bounds, so a rotation preview behaves like a real cutout for render/drag/hit-test. |
| `inflateAroundCenter(rect, factor)` | Grows a `{left,top,width,height}` rect around its own center. |
| `inflateBounds(bounds, factor)` | Same, for `{left,top,right,bottom}` bounds. |
| `clampCutoutOffset(offset, alphaBounds, imageSize)` | Clamps a drag offset (natural-image pixels) so the object's opaque bounds stay inside the photo. |
| `getBoundsStageRect(bounds, offset, renderedRect, naturalSize)` | Maps alpha bounds + offset from natural pixels into on-stage CSS pixels. |
| `ALPHA_HIT_THRESHOLD = 10` | Minimum alpha (0–255) counted as a hit-test hit. |
| `buildHitTestOrder(objects, selectedObjectId)` | Hidden objects filtered out, reversed to topmost-first, selected object always moved to front. |
| `toNaturalPoint(localX, localY, renderedRect, naturalSize)` | Converts a stage-local pointer position to natural-image coordinates; `null` if the point falls in the letterbox area. |

## `utils/preview.ts`

[`react-front/src/utils/preview.ts`](../../react-front/src/utils/preview.ts)

`PREVIEW_MAX_WIDTH = 640` (long edge, downscale-only). `composeSessionPreview(backgroundSrc, layers: PreviewLayer[], naturalSize)` draws the background then every layer (shifted by its offset) onto a scaled offscreen canvas and returns a JPEG `data:` URL at quality `0.82` with the `data:` prefix stripped — filtering to visible-only objects is the caller's job (`WorkspaceScreen`), not this function's. It fetches source images with `{mode:"cors", cache:"reload"}` rather than `crossOrigin` on an `<img>`: the stage's own plain `<img src={photoSrc}>` (no `crossOrigin`) loads the identical cache-busted background URL moments earlier as a `no-cors` navigation, which the browser can cache as an opaque, headerless response — a later `cors`-mode fetch of that same URL can reuse that opaque cache entry and fail CORS validation even though the server's real response carries proper headers. `cache: "reload"` forces a genuine network round-trip that sidesteps the collision (confirmed via devtools as the cause of dashboard thumbnails silently never updating after the first upload-time preview).

## `utils/time.ts`

[`react-front/src/utils/time.ts`](../../react-front/src/utils/time.ts)

`formatEditedAgo(iso)` — coarse relative-time label ("edited just now" / "edited Nm ago" / "edited Nh ago" / "edited Nd ago"), `null` for unparseable input. `byMostRecentlyEdited(a, b)` — comparator over `{ last_changed: string | null }`, newest first, sessions with no timestamp sort last.

## `types/session.ts`

[`react-front/src/types/session.ts`](../../react-front/src/types/session.ts)

Client-only view models derived from the API DTOs in `types/api.ts`, carrying state the backend never sees (drag offset, hidden flag, GLB buffer, rotation).

```ts
export interface CutoutObject {
  objectId: number;
  uuid: string | null;       // null only for pre-UUID legacy session data
  name: string | null;
  cutoutSrc: string;
  cutoutAlphaBounds: CutoutAlphaBounds | null;
  normalizedClickPos: ClickPosition | null;
  glbData: ArrayBuffer | null;
  rotation: ObjectRotation | null;   // local-only, lost on session restore
  hidden: boolean;                    // local-only visibility toggle
  offset: ClickPosition;              // persisted via setObjectOffset
  sourceElevationDeg: number;
}
```

`ObjectRotation { pose, previewSrc, src, bounds, status: "pending" | "ready" | "error" }` — `previewSrc` is the viewer snapshot shown immediately; `src` is the real synthesized PNG once it lands. Re-rotating always overwrites this from the pristine cutout, since the backend never mutates `cutoutSrc`'s file in the rotate path.

`effectiveCutoutSrc(obj, showOriginal)` / `effectiveCutoutBounds(obj, showOriginal)` are the **single place** that decides, per object, whether the stage should show the pristine cutout or the rotated result — used consistently by the stage render, hit-testing, drag-clamp bounds, and `ObjectRail` thumbnails. This matters because `rotation` must never be written into `cutoutSrc`/`cutoutAlphaBounds` directly: `useSessionSync`'s reconcile unconditionally overwrites those two fields from server truth on every sync tick, and would silently erase an in-progress rotation if it lived there.

`PendingInpaintJob { jobId, maskId, normalizedClickPos, startedAt }` and `SegmentPickerState = {status:"idle"} | {status:"loading"} | {status:"choosing", maskOptions}` back the segment/inpaint UI described above.

## `types/api.ts`

[`react-front/src/types/api.ts`](../../react-front/src/types/api.ts)

Mirrors the backend's Pydantic models in [`fastApi-app/schemas/image.py`](../../fastApi-app/schemas/image.py) field-for-field — see [backend/schemas.md](../backend/schemas.md) for the authoritative field tables (`ObjectInfo`, `ObjectMetadataResponse`, `UpdateObjectRequest`, `DuplicateObjectResponse`, `NovelViewRequest`/`Response`, `SessionSyncCheckResponse`, `SessionInfo`, etc.). No codegen exists — a backend schema change requires a manual edit here. `VerifyMode` is `"manual" | "auto"`. `SegmentRequest` extends `ClickRequest` with optional `verify`; `InpaintMaskRequest` also has optional `verify`. `InpaintMaskResponse` and `ObjectMetadataResponse`/`ObjectInfo` extend the shared `cutout_bounds`/offset fields documented in `backend/schemas.md`.

## `types/debug.ts`

[`react-front/src/types/debug.ts`](../../react-front/src/types/debug.ts)

Mirrors [`fastApi-app/schemas/debug.py`](../../fastApi-app/schemas/debug.py) (`DebugCheckResult`, `DebugValidationResponse` — see [backend/schemas.md](../backend/schemas.md#debug)) plus the query-param shapes for the two PNG endpoints: `DepthMapOptions { strategy, model, colormap }`, `SamEverythingOptions { source, depthStrategy, depthModel, pointsPerSide, predIouThresh, stabilityScoreThresh, minMaskRegionArea, alpha }`, and the local-only `DebugImageResult { objectUrl, elapsedMs, maskCount }` returned by `api/debug.ts`. Kept separate from `types/api.ts`, which mirrors `schemas/image.py`.

`DebugScreen`'s own panel state is a small discriminated union defined inline (not in this file): `PanelState<T> = {status:"idle"} | {status:"running"} | {status:"done", data:T} | {status:"error", message:string}`, one instance per panel (validation, depth, SAM).
