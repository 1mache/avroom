# User Flow

## Dashboard → upload → workspace

```mermaid
sequenceDiagram
    actor User
    participant Dash as DashboardScreen
    participant Up as UploadScreen
    participant WS as WorkspaceScreen
    participant API as "api/images.ts"
    participant Backend as "FastAPI backend"

    User->>Dash: land on app (App boots into dashboard)
    Dash->>API: getSessions()
    API->>Backend: GET /images/sessions
    Backend-->>Dash: SessionInfo[] (sorted newest-edited-first)

    User->>Dash: click "New session"
    Dash->>Up: App switches route to upload
    User->>Up: choose/drag file
    Up->>API: uploadImage(file)
    API->>Backend: POST /images/upload
    Backend-->>Up: ImageUploadResponse (image_id)
    Up->>WS: App switches route to workspace {uid}

    User->>Dash: (alt) click an existing SessionCard
    Dash->>WS: App switches route to workspace {uid}
```

`WorkspaceScreen` is mounted `key={uid}`, so opening a different session always remounts the editor from scratch rather than reusing state. The back arrow in the workspace `Toolbar` routes back to the dashboard, which re-fetches the session list.

## Segment → choose mask → inpaint

```mermaid
sequenceDiagram
    actor User
    participant WS as WorkspaceScreen
    participant Jobs as useSessionJobs
    participant API as "api/images.ts"
    participant Backend as "FastAPI /images"

    User->>WS: press scissors (arms cutMode)
    User->>WS: click a point on the photo
    WS->>Jobs: runSegment(x, y)
    Jobs->>API: segmentImage({image_id, x, y})
    API->>Backend: POST /images/segment
    Backend-->>Jobs: SegmentResponse(masks[])
    Jobs-->>WS: segmentState = choosing
    WS-->>User: MaskPickerModal

    User->>WS: pick a candidate
    WS->>Jobs: selectMask(mask_id, normalizedClickPos)
    Jobs-->>WS: picker closes immediately, PendingInpaintJob added to ObjectRail
    Jobs->>API: inpaintMask({image_id, mask_id})  (detached)
    API->>Backend: POST /images/inpaint
    Backend-->>Jobs: InpaintMaskResponse (object_id, object_uuid, background_b64, cutout_b64)
    Jobs-->>WS: pending job removed, new CutoutObject appended + auto-selected, backgroundSrc updated
    WS-->>User: preview thumbnail re-captured (debounced 500ms)
```

Because `selectMask` fires the inpaint request detached, the user can immediately click a new point and start a second segment/inpaint while the first is still running — the backend's per-session canvas-writer lock and region leases (`docs/backend/concurrency.md`) make this safe, and `useConflictNotices` surfaces any resulting 409 as a dismissible inline notice rather than a hard error.

## Multiple objects, drag, duplicate, delete

All of a session's objects stay composited on the inpainted background simultaneously — each has its own `hidden` flag and drag `offset` (client-only visibility, persisted position). Selection (`selectedObjectId`) is independent of visibility and starts `null` on both fresh upload and session restore.

- **Select**: click an object's row in `ObjectRail`, or click/drag it directly on the stage (alpha-precise hit-testing — see [components.md](components.md)). Hiding the selected object clears selection; a newly created object auto-selects.
- **Drag**: pointer-down on a hit object starts a drag; position updates locally on every `pointermove` (clamped to the object's visible bounds), and the final offset is persisted with one `PATCH` (`setObjectOffset`) on `pointerup` — not on every move.
- **Duplicate**: the toolbar's copy button (disabled without a selection, while duplicating, or while rotating) calls `useSessionJobs.duplicateObject`, which clones the object server-side (`POST /images/objects/{uuid}/duplicate`), fetches the clone's full metadata, and selects it. The clone lands nudged ~15% of its own width to one side of the source, not exactly on top of it (server-computed, see `backend/api-endpoints.md`).
- **Delete**: the toolbar's trash button opens a `ConfirmDialog`; confirming calls `useSessionJobs.deleteObject`, which requires the object to have a `uuid` (pre-UUID legacy objects can't be deleted) and permanently removes its cutout, GLB, and novel-view caches server-side. The background keeps the object's inpainted hole — deletion never repaints it.
- Both duplicate and delete trigger a debounced dashboard-preview re-capture (`WorkspaceScreen`'s `onMutated` wiring).

## Rotation

Pressing **Rotate** with an object selected either opens the 3D angle picker immediately (if a GLB is already cached for that object) or first generates one (`POST /3d/test-3d`, cached via `GET /3d/{uid}/{objectId}`). While the picker is open, the selected object's 2D cutout is replaced in place by the `Model3DFrame` viewer at the same on-stage rect. Orbiting the model measures azimuth/elevation deltas from the pose it started at. Pressing Rotate again (or Enter) captures those deltas plus a snapshot, closes the picker, and fires `useSessionJobs.commitRotation` detached against `POST /images/novel-view` — the snapshot shows immediately as a placeholder and is swapped for the real synthesized image when the response lands. Escape cancels with no request. A per-object "show original" toggle in `ObjectRail` reverts to the pristine cutout; rotating again always restarts from that pristine cutout, since the backend never overwrites it in the rotate path.

## Session restore and background sync

On opening a session, `WorkspaceScreen` calls `getUidCacheStatus(uid)` for the background/name, then `getSessionObjects(uid)` for the full object list if a cutout exists — restored objects get `hidden = false` and no `rotation`/`glbData` (those are local-only and lost across a restore). From then on, `useSessionSync` polls `POST /images/{uid}/sync-check` every 2 seconds **only while there's pending work** (an in-flight segment/inpaint/duplicate/etc.), plus once on window focus and tab-visibility change regardless of pending work. A stale-timestamp response triggers a merge (not a full replace) of server truth into local state, so local-only fields like `offset`, `hidden`, and `glbData` survive a reconcile untouched.

## Pipeline debug screen

```mermaid
sequenceDiagram
    actor User
    participant Dash as DashboardScreen
    participant Debug as DebugScreen
    participant API as "api/debug.ts"
    participant Backend as "FastAPI /debug"

    User->>Dash: click flask icon
    Dash->>Debug: App switches route to debug
    User->>Debug: drag/drop or choose a photo
    User->>Debug: click "Run all"

    Debug->>API: validateImageDebug(file)
    API->>Backend: POST /debug/validate
    Backend-->>Debug: DebugValidationResponse (always 200)
    Debug-->>User: technical + content check rows render, PASS/FAIL badge

    Debug->>API: debugDepthMap(file, options)
    API->>Backend: POST /debug/depth-map
    Backend-->>Debug: PNG bytes + X-Elapsed-Ms
    Debug-->>User: depth-map panel renders, regardless of the validation verdict above

    Debug->>API: debugSamEverything(file, options)
    API->>Backend: POST /debug/sam-everything
    Backend-->>Debug: PNG bytes + X-Mask-Count + X-Elapsed-Ms
    Debug-->>User: SAM panel renders

    User->>Debug: click a rendered PNG
    Debug-->>User: DebugLightbox full-screen viewer (Esc/backdrop closes)
```

A separate screen reached from the dashboard header (`App.tsx`'s `{screen:"debug"}` route), not part of the session workspace — no `uid`, no session created, nothing written to disk. See [components.md](components.md#debugscreen) for the panel/state breakdown and [backend/api-endpoints.md](../backend/api-endpoints.md#debug-endpoints) for the three endpoints it drives.

Each of the three panels (Validation, Depth map, SAM segment-everything) can also be re-run individually with its own knobs, independent of `Run all` — a panel's knob changes only take effect on its next `Re-run`, not live. Depth and SAM stages always run whether or not the validation stage passed; that's the point of the screen. `Run all` runs the three sequentially rather than in parallel, since SAM shares the process-wide GPU lock with everything else in inline mode (`docs/backend/concurrency.md`) — firing all three at once would just serialize behind the lock anyway.

## Dashboard preview thumbnails

Every mutation that changes what a session looks like (inpaint, rotation, rename, duplicate, delete, hide/show, and drag-end) triggers a debounced (500ms) client-side composite of the background plus every visible cutout (`composeSessionPreview`), posted to `POST /images/{uid}/preview`. The dashboard's `SessionCard` reads it back via a cache-busted `GET /images/{uid}/preview` URL, falling back to a placeholder icon if the request 404s (no preview yet — `POST /images/upload` writes an initial one server-side, so this should only happen transiently).
