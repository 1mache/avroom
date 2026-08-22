# Components

## `DashboardScreen`

[`react-front/src/components/layout/DashboardScreen.tsx`](../../react-front/src/components/layout/DashboardScreen.tsx)

Props: `{ onOpenSession: (uid: string) => void; onNewSession: () => void; onOpenDebug: () => void }`.

The app's home screen. Owns `sessions: SessionInfo[]`, `loadState: "loading" | "ready" | "offline"`, `pendingDeleteUid: string | null`, `isDeleting`, `error`.

- On mount, fetches `getSessions()` and sorts with `byMostRecentlyEdited` (`utils/time.ts`) — newest `last_changed` first, sessions with no timestamp sort last. A fetch failure sets `loadState = "offline"` and renders a retry state instead of the error modal.
- Renders a "New session" CTA that calls `onNewSession`, a scrollable grid of `SessionCard`s (only the grid scrolls — the CTA stays reachable regardless of list length), a loading-skeleton state, and an empty state when there are no sessions.
- Delete flow: a `SessionCard`'s trash button calls `onRequestDelete(uid)`, which sets `pendingDeleteUid`; a `ConfirmDialog` confirms; on confirm, `deleteSession(uid)` is awaited and the session is filtered out of local state on success, or `error` is set (generic error modal) on failure.
- Clicking a `SessionCard` calls `onOpenSession(uid)`, which `App.tsx` routes into the workspace.
- The header (`.dash-header`) carries a right-aligned (`.dash-header-end`, `margin-left: auto`) icon-only button (`FlaskIcon`, `data-tip="Pipeline debug"`) that calls `onOpenDebug`, routing to `DebugScreen`. Always visible regardless of whether the backend's `DEBUG_ENDPOINTS` is on — a disabled backend surfaces as a 404 inside each panel, not a hidden button (no extra dashboard-load request to probe first).

## `UploadScreen`

[`react-front/src/components/layout/UploadScreen.tsx`](../../react-front/src/components/layout/UploadScreen.tsx)

Props: `{ onCancel: () => void; onUploaded: (uid: string) => void }`.

The file-intake step between dashboard and workspace. Constants `ACCEPTED_TYPES = ["image/jpeg","image/png","image/webp"]` and `MAX_BYTES = 25 * 1024 * 1024` mirror the backend's upload gate for instant client-side feedback before a round trip.

- State: `file`, `previewUrl` (object URL, revoked on replace/unmount), `phase: "choosing" | "checking" | "rejected"`, `rejection`, `isDragOver`.
- Accepts a file via drag-drop or the file picker; `acceptFile` runs the client-side type/size check and either sets a preview or moves to `phase: "rejected"` with a reason.
- Starting the upload (`handleStart`) calls `uploadImage(file)`; on success it calls `onUploaded(response.image_id)`. On an `ApiError` with `status === 422` it shows the backend's validation-rejection detail text as a normal outcome (not a crash); any other failure shows a generic message.
- The back button is disabled while `phase === "checking"`.

## `WorkspaceScreen`

[`react-front/src/components/layout/WorkspaceScreen.tsx`](../../react-front/src/components/layout/WorkspaceScreen.tsx)

Props: `{ uid: string; onExit: () => void }`.

The editor. The largest component in the tree — it owns most local UI state directly and composes the three session hooks ([state-and-types.md](state-and-types.md)) plus every workspace widget.

### Session boot

On mount (`[uid]`-keyed effect; `App` remounts this component on `uid` change so it never needs to re-run for the same session):

1. Sets `originalSrc` to `${API_BASE_URL}/images/${uid}/original` immediately (cheap, always safe to show).
2. Calls `getUidCacheStatus(uid)` → sets `sessionName`, sets `backgroundSrc` if `has_background`.
3. If `has_cutout`, calls `getSessionObjects(uid)` and `jobs.loadRestoredObjects(...)`.
4. Seeds sync via `recordLocalMutationRef.current()`.
5. On any failure, falls back to `sessionName = uid`.

While `photoSrc` (`backgroundSrc ?? originalSrc`) hasn't resolved, the stage renders a plain `"Opening the session"` placeholder (`.stage-message`) — there is no dedicated offline UI here (that lives in `DashboardScreen`'s session-list fetch).

### Stage geometry and hit-testing

- `measureStage` + a `ResizeObserver` track the stage's rendered size; `getContainedImageRect` (`utils/stageGeometry.ts`) derives the actual `object-fit: contain` rect so overlays line up with the visible image, not the outer container.
- Hit-testing is **alpha-precise, not DOM stacking**: cutout PNGs are full-image-sized with transparency outside the object, so a topmost DOM layer would swallow every click. `hitCanvasesRef` (a `Map<number, HitCanvasEntry>`) holds one offscreen `<canvas>` per object, invalidated whenever that object's *effective* cutout src changes (not just when the id first appears — rotation swaps the silhouette in place). `sampleObjectAlpha` reads a 1×1 pixel; a missing canvas is treated as fully opaque so a brand-new object is clickable before its canvas finishes building.
- A single transparent `.stage-input` div owns all pointer-down handling. `handleStagePointerDown`: if `cutMode` is armed, the click becomes the segmentation seed (`jobs.runSegment(...)`) and disarms cut mode; otherwise it walks `buildHitTestOrder(objects, selectedObjectId)` (topmost-first, selected object tested first) and alpha-samples each candidate against `ALPHA_HIT_THRESHOLD`.

### Selection, cut, rotate, duplicate, delete

- `selectObject` always forces `rotateMode = false` and `cutMode = false` and clears `pickPoint` — changing selection always exits whatever tool was active.
- `handleCut` arms `cutMode` (and clears rotate / area / any pick point); the next stage click fires the segment request (`verifyMode` from the toolbar radio) and disarms itself. The area tool arms a box drag that POSTs `/images/{uid}/batch` with `verify=auto`. Escape cancels while `cutMode || rotateMode || areaMode` is true.
- `handleRotate`: if the picker is already open, delegates to `commitCurrentRotation`. Otherwise it requires a selection; if the object's GLB is already cached (`glbData`) it opens the picker immediately, otherwise it sets `isPreparing3D`, tries `fetchCached3DModel` then falls back to `generate3DModel`, stores the buffer via `jobs.setObjects`, and only opens the picker if the selection hasn't moved on in the meantime.
- `commitCurrentRotation`: captures the viewer's pose + a canvas snapshot via `model3DFrameRef.current.capture()` **before** closing the picker, computes the on-stage bounds by inflating the object's existing alpha bounds by `MODEL_3D_FRAME_PADDING`, composites the snapshot onto a full-canvas transparent PNG (`compositePreviewOntoCanvas`), then calls `jobs.commitRotation(...)` — falling back to the raw (uncomposited) snapshot if compositing throws.
- `handleCopy` and `handleDeleteObject` both require `selectedObject?.uuid` to exist; a legacy pre-UUID object surfaces an explicit "This object is from an older session and can't be deleted" error instead of silently no-op'ing. Delete opens a `ConfirmDialog` (`pendingDeleteObjectId`); confirming awaits `jobs.deleteObject(...)`.

### Drag

A pointer-down inside `.stage-input` that hits an object (rather than arming cut mode) starts a drag: `dragStateRef` is set, `document.body` gets an `is-dragging-object` class, and the object is selected. A separate effect attaches window-level `pointermove`/`pointerup`/`pointercancel` listeners only while `isDragging` is true — converting screen-space pointer delta into natural-image pixels via the rendered rect and natural size, clamping through `clampCutoutOffset`, and calling `jobs.updateOffset` continuously (local-only, no network). On pointer-up (`finishDrag`) the drag state clears, the dashboard preview thumbnail is captured, and the final offset is persisted with `setObjectOffset(uuid, x, y)` — a single PATCH per drag, not per pointermove.

### Preview thumbnail capture

`PREVIEW_DEBOUNCE_MS = 500`. A ref-stashed function (`capturePreviewRef`) composites the current background plus every visible cutout at its offset via `composeSessionPreview` (`utils/preview.ts`) and calls `saveSessionPreview(uid, ...)`, debounced 500ms. It fires from two places:

1. `handleMutated` — called as the `onMutated` callback passed into `useSessionJobs`, so it runs after every hook-driven mutation (inpaint success, rotation, rename, duplicate, delete, hide/show).
2. Directly from `finishDrag` at drag-end, since drags never go through `useSessionJobs` and so never trigger `onMutated` on their own.

### Rendering

Renders `Toolbar` (wired to nearly all local + hook state), a `<main className="stage">` containing the background photo, one `.stage-cutout` `<img>` per visible object (z-index keeps the selected object on top regardless of creation order), the transparent `.stage-input` hit layer, a pick-point marker while `cutMode` is armed, the `Model3DFrame` in place of the selected object's 2D cutout while `rotateMode` is on, a 4-corner `.selection-frame` around the selected object, conflict notices (`useConflictNotices`), and `ObjectRail`. Outside `<main>`: `MaskPickerModal` (while choosing a segmentation candidate), the object-delete `ConfirmDialog`, and a generic error modal.

## `DebugScreen`

[`react-front/src/components/layout/DebugScreen.tsx`](../../react-front/src/components/layout/DebugScreen.tsx)

Props: `{ onExit: () => void }`.

Reachable from the dashboard header's flask icon. Upload a photo, click it to set a seed point, and see validation, depth, SAM-everything, auto mask pick, and inpaint-verify traces — nothing here creates a session or writes to disk.

- **Source strip** reuses `UploadScreen`'s dropzone markup/classes. Clicking the preview sets natural `(x, y)` via `toNaturalPoint` (red marker). Auto mask pick and inpaint verify stay disabled until a click exists. Picking a new file bumps `runTokenRef` and resets all pipeline panels plus the click.
- **Panels**: Validation, Depth map, SAM segment-everything, Auto mask pick, Inpaint verification, plus 3D viewer. Each independently `Re-run`-able. Errors render **inside the panel**.
- **`Run all`** awaits validation → depth → SAM only. The two verify panels are click-gated and GPU-heavy, so they are not part of `Run all`. The normal-map panel is Generate-only (Metric3D) and also excluded from `Run all`.
- **Normal map panel** — `POST /debug/normal-map` via `debugNormalMap`; hub model select; click the result image to read approximate nx/ny/nz from the 8-bit PNG.
- Auto mask pick shows every candidate (preview, CLIP crop, score, reason) and highlights the winner; clicking a card sets `selectedMaskIndex` for inpaint verify (winner auto-selected on a successful pick).
- Inpaint verification shows LaMa, then each CLIP retry (candidate, crop, scores, SD params in, verifier JSON out) and the final sharpened image.
- **Staleness guard**: `runTokenRef` is bumped on every new file pick; each async run captures its own token and checks it before committing state (same pattern as `useSessionJobs`'s `imageIdRef`), so a slow response for a since-discarded photo can never overwrite a fresher run's result. A discarded-but-still-inflight PNG result has its object URL revoked immediately rather than held.
- **Object URL lifecycle**: `heldUrlsRef` (a `Set<string>`) tracks every blob URL the depth/SAM panels have ever produced. Re-running a panel revokes its previous `done` result's URL before storing the new one; unmounting revokes everything still held, plus the source preview URL (read through a `previewUrlRef` mirror, since the unmount effect's closure would otherwise only ever see the initial-render value).
- **Full-screen viewer**: clicking either rendered PNG opens `DebugLightbox`, a small component defined in the same file (not `ConfirmDialog`/`MaskPickerModal` — those are shaped for decisions, not viewing). Fixed overlay on `.modal-backdrop`'s z-index band, image at `object-fit: contain` on the app's transparency checkerboard, closed by Esc, backdrop click, or a close button.
- Depth/SAM model fields are `<input list=...>` bound to a shared `<datalist id="debug-depth-models">` (5 known HF checkpoints) — a dropdown that still accepts free text.

## `Toolbar`

[`react-front/src/components/workspace/Toolbar.tsx`](../../react-front/src/components/workspace/Toolbar.tsx)

Purely presentational and controlled — owns no state of its own beyond one derived value, `objectToolsDisabled = !hasSelection`.

Left to right: **back** arrow (always enabled, calls `onBack` → `WorkspaceScreen`'s `onExit` → dashboard) · editable **session name** (Enter saves) · **scissors** (arms `cutMode`; `is-armed` class + `aria-pressed` while active; never disabled) · **Manual/Auto** radio (`role="radiogroup"`, cutout-scoped, always enabled) switching `verify` on the next segment/inpaint · **rotate** (icon swaps to a checkmark while `rotateMode` is on, a spinner while `isPreparing3D`; disabled when nothing is selected or while preparing) · **copy/duplicate** (spinner while `isDuplicating`; disabled with no selection, while duplicating, or while `rotateMode` is on) · **smart-paste** switch (`role="switch"`; when on, drag-end calls `POST /images/objects/{uuid}/smart-paste` for depth rescale) · a status readout string (only rendered when non-null; shows `smart pasting` while the request is in flight) · **trash** (red/`is-danger`; spinner while `isDeleting`; disabled with no selection, while deleting, or while `rotateMode` is on).

Every object-scoped tool (rotate, copy, smart-paste, trash) **greys out** via the `disabled` attribute rather than unmounting when nothing is selected, so the toolbar never reflows. Icons carry no text labels; they self-identify on hover via the shared `[data-tip]` CSS tooltip.

## `ObjectRail`

[`react-front/src/components/workspace/ObjectRail.tsx`](../../react-front/src/components/workspace/ObjectRail.tsx)

Props: `objects`, `pending` (in-flight inpaint placeholders), `selectedObjectId`, `showOriginalIds`, `disabled`, `onSelectObject`, `onToggleHidden`, `onToggleShowOriginal`, `onRenameObject`.

Replaces the old `ObjectPanel`. `CLOSE_DELAY_MS = 220`: the rail opens immediately on `pointerenter` (cancelling any pending close) and, on `pointerleave`, schedules a close after 220ms — unless a rename input is currently focused (`editingObjectId !== null`), so the panel never yanks an input out from under mid-typing.

Two layers live in the DOM simultaneously and are shown/hidden purely via CSS keyed off a `data-open` attribute on the root:

- **`.rail-spine`** — the always-visible collapsed state. One notch per object plus one per pending job; modifier classes `is-selected`, `is-hidden`, `is-working` (driven by `rotation?.status === "pending"`, or unconditionally true for pending inpaint jobs).
- **`.rail-panel`** — the full slide-out list. Each row has a thumbnail (showing `effectiveCutoutSrc`, with a spinner badge while a rotation is pending), an editable name (double-click to rename; Enter commits, Escape discards via a `cancelledEditRef` flag that disambiguates from the commit-on-blur path), an eye/eye-off visibility toggle (always present), and a revert-to-original toggle that only renders — rather than greying out — when the object actually has a ready rotation result (`obj.rotation?.status === "ready"`).

Pending inpaint jobs render as a spinner + "Removing" placeholder row (no thumbnail yet, since `object_id` doesn't exist until the response lands). An empty state ("Cut an object out of the photo and it lands here.") shows when there are no objects and no pending jobs.

## `SessionCard`

[`react-front/src/components/dashboard/SessionCard.tsx`](../../react-front/src/components/dashboard/SessionCard.tsx)

Props: `{ uid, name: string | null, lastChanged: string | null, onOpen, onRequestDelete }`.

One dashboard grid tile. Shows `sessionPreviewUrl(uid, lastChanged)` (cache-busted by `lastChanged`) as the thumbnail; on `<img onError>` it flips a local `previewFailed` flag and swaps to a placeholder icon + "No preview yet" instead of a broken image. A separate hover-revealed trash button calls `onRequestDelete(uid)`. The caption shows `name ?? "Untitled session"` and `formatEditedAgo(lastChanged)` (`utils/time.ts`), which falls back to "never edited".

## `ConfirmDialog`

[`react-front/src/components/widgets/ConfirmDialog.tsx`](../../react-front/src/components/widgets/ConfirmDialog.tsx)

Props: `{ title, body, confirmLabel, cancelLabel = "Cancel", destructive = false, busy = false, onConfirm, onCancel }`. Shared by `DashboardScreen` (session delete) and `WorkspaceScreen` (object delete) — no other consumers.

Escape and backdrop-click both cancel unless `busy`. The confirm button is `autoFocus`, styled `is-danger` when `destructive` else `is-primary`, and shows a spinner in place of its label while `busy`; both buttons are disabled while `busy`.

## `MaskPickerModal`

[`react-front/src/components/widgets/MaskPickerModal.tsx`](../../react-front/src/components/widgets/MaskPickerModal.tsx)

Props: `{ masks: SegmentMaskOption[], onSelect: (maskId: string) => void, onClose: () => void }`. Stateless.

Renders a grid of candidate cutout previews (`data:image/{format};base64,{cutout_b64}`, not raw black/white masks) with zero-padded index labels. Clicking a card calls `onSelect(mask.mask_id)`. Backdrop click and the close button always dismiss unconditionally — by design, selecting a mask closes the picker immediately and fires the inpaint request detached (see `useSessionJobs.selectMask` in [state-and-types.md](state-and-types.md)), so there is no in-flight state left for the modal to protect.

## `Model3DFrame`

[`react-front/src/components/widgets/Model3DFrame.tsx`](../../react-front/src/components/widgets/Model3DFrame.tsx)

`forwardRef<Model3DFrameHandle, Props>`. Props: `{ glbData: ArrayBuffer | null, className?, style? }`. Exposes `MODEL_3D_FRAME_PADDING = 1.5` and `Model3DFrameHandle.capture(): RotationCapture | null`.

Builds a full Three.js scene/camera/renderer/`OrbitControls` (damping on, panning disabled, target pinned to the origin) per `glbData` change, loads the GLB via `GLTFLoader.parse`, normalizes its scale and recenters it, wraps it in an `oriented` group carrying a correction matrix (`glbToViewRotation()`, currently identity — Hunyuan3D-2.1's GLBs already come back Y-up with the photographed face toward +Z, matching `_GLB_TO_VIEW_ROTATION` in the backend's mesh-render novel-view strategy; the hook exists for a future generator with a different axis convention), then fits it to the viewport by sampling real projected vertices (not bounding-box corners, so concave/curved objects still fill the frame) rather than a simple bounding box. Lighting is a neutral-white studio rig (ambient + key/fill/rim, all white) plus a headlight parented to the camera so whatever face is being orbited toward stays lit; material `metalness` is clamped low so glTF's metallic-by-default materials don't render near-black.

`capture()` reports **deltas** from the pose the viewer started at (captured once via `initialAzimuthalRef`/`initialPolarRef`), not absolute angles — and inverts the elevation delta (`initialPolar - currentPolar`) because Three's polar angle shrinks as the camera rises. It also reads back a PNG snapshot via `renderer.domElement.toDataURL(...)`, which requires `preserveDrawingBuffer: true` on the renderer or the readback comes back blank.

`WorkspaceScreen` treats this component purely as an angle picker, not a standalone preview: its only two effects on the rest of the app are the `capture()` ref method and continuous rendering. All rotation-commit logic (building the request, updating object state) lives in `WorkspaceScreen.commitCurrentRotation`.

## `icons.tsx`

[`react-front/src/components/icons.tsx`](../../react-front/src/components/icons.tsx)

A shared `Svg` wrapper (24-unit viewBox, `strokeWidth: 1.6`, round caps/joins, `fill: none`, `stroke: currentColor`) gives every icon a consistent hand-drawn look. Exports one `React.FC<IconProps>` per icon (`IconProps = { size?: number }`, default `18`): `BackIcon`, `ScissorsIcon`, `RotateIcon`, `CopyIcon`, `SmartPasteIcon`, `TrashIcon`, `CheckIcon`, `EyeIcon`, `EyeOffIcon`, `RevertIcon`, `PlusIcon`, `PhotoIcon`, `FlaskIcon`. No icon carries a text label — every usage relies on the `[data-tip]` hover tooltip (see [styling.md](styling.md)).

## CSS roles

See [styling.md](styling.md) for the full section-by-section map of `style.css`. In short: `.stage*` classes belong to `WorkspaceScreen`, `.toolbar*`/`.tool-*` to `Toolbar`, `.rail*` to `ObjectRail`, `.dash*`/`.session-*` to `DashboardScreen`/`SessionCard`, `.dropzone*`/`.upload-*` to `UploadScreen`, `.debug-*` to `DebugScreen` (reusing `.dropzone*`/`.btn*`/`.modal-backdrop`/`.checker` where the shapes already match), and `.modal*`/`.mask-*`/`.confirm-*`/`.btn*` are shared across `ConfirmDialog`, `MaskPickerModal`, and the inline error modals in both screens.
