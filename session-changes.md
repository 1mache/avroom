# Multi-Object Segmentation — Session Changes

Branch: `dima` · Base commit: `499b36b` · Head: `a27e008`

---

## Overview

Added support for multiple segmented objects per session. Key decisions made during planning:
- **Progressive removal** — each new object is cut from the latest cumulative background (previous removals already applied), not the original upload.
- **Image frame always shows the latest background.** Selecting an object in the side panel only changes which object's cutout/3D the bottom checkboxes target.
- **Object id = integer counter per session** (0, 1, 2…). Existing single-object files with no object id are treated as object 0 (back-compat).
- **Whole-session delete only** — no per-object delete this iteration.

---

## New Files

### `fastApi-app/core/object_storage.py` (174 lines)

Central path-naming module. All `{uid}_{object_id}_…` filename construction lives here.

| Function | Lines | Returns |
|---|---|---|
| `object_cutout_path(base_dir, uid, object_id)` | 18–32 | `{uid}_{object_id}_cutout.png` unconditionally |
| `resolve_object_cutout_path(base_dir, uid, object_id)` | 35–60 | numbered path; for id 0 only, falls back to legacy `{uid}_cutout.png` if numbered absent |
| `object_glb_path(glb_dir, uid, object_id)` | 63–77 | `{uid}_{object_id}.glb` unconditionally |
| `resolve_object_glb_path(glb_dir, uid, object_id)` | 80–104 | same fallback for id 0 to legacy `{uid}.glb` |
| `list_object_ids(base_dir, uid)` | 107–138 | regex `^{uid}_(\d+)_cutout\.png$` — candidate files (`_mask_N_`) are NOT matched because `\d+` won't match `mask_3`. Also includes 0 if legacy `{uid}_cutout.png` exists. Returns sorted `list[int]`. |
| `next_object_id(base_dir, uid)` | 141–157 | `max(list_object_ids()) + 1`, or 0 if empty |
| `current_background_path(base_dir, uid)` | 160–174 | `{uid}_background.png` (single cumulative canvas) |

### `react-front/src/components/widgets/ObjectPanel.tsx` (91 lines)

Right slide-in panel component for switching between / adding objects.

- Props: `objects: ObjectEntry[]`, `activeObjectId`, `isAddingObject`, `disabled`, `onSelectObject`, `onAddObject`, `collapsed`, `onToggleCollapsed`
- Uses minimal `ObjectEntry { objectId, cutoutSrc }` interface — does not import `CutoutObject` from MainPage.
- Side column (always visible, 28px): collapse toggle arrow + always-accessible `+` button. The `+` is outside the collapsible body so it stays reachable when the panel is collapsed.
- Collapsible body (150px when expanded): scrollable thumbnail list with checkerboard transparency background.
- Active object thumbnail gets accent border (`is-active`).
- `+` button in side column highlights when `isAddingObject=true`.
- All interactive elements respect `disabled` prop; inner handlers also guard on `disabled` as a second layer.

---

## Modified Files

### `fastApi-app/core/image_processing.py`

**Added `load_canvas_bytes` (lines 105–138):**
- Checks if `{uid}_background.png` exists; returns it if so (progressive removal canvas).
- Falls back to original upload via `load_image_bytes` if no background yet.
- Logs at DEBUG (not INFO — hot path).

**Changed `segment_candidates_on_image` (line 290):**
- `load_image_bytes(...)` → `load_canvas_bytes(...)` — segmentation now runs on the latest background, not the original.

**Changed `inpaint_selected_mask_on_image` (lines 326–327):**
- `load_image_bytes(...)` → `load_canvas_bytes(...)`.
- Local var `original_bgr` → `source_bgr` (the source may be the canvas, not the original).
- Result: inpainting accumulates — each removal stacks on the previous one.

---

### `fastApi-app/schemas/image.py`

**`InpaintMaskResponse` (lines 183–193):** Added `object_id: int` field (`default=0`, `ge=0`). Default 0 preserves the legacy inpaint route call-site; `inpaint_mask` in routes.py now supplies the real allocated id.

**New `ObjectInfo` model (lines 196–218):** Fields: `object_id`, `cutout_b64`, `format`, `cutout_bounds?`, `has_3d`.

**New `ObjectListResponse` model (lines 221–231):** Fields: `uid`, `objects: list[ObjectInfo]`.

---

### `fastApi-app/api/routes.py`

**New imports (top of file):** `current_background_path`, `list_object_ids`, `next_object_id`, `object_cutout_path`, `object_glb_path`, `resolve_object_cutout_path`, `resolve_object_glb_path` from `core.object_storage`. `ObjectInfo`, `ObjectListResponse` from `schemas.image`.

**`inpaint_mask` POST `/images/inpaint` (lines ~315–360):**
- Allocates `object_id = next_object_id(storage_dir, request.image_id)` before any writes.
- Background written via `current_background_path(...)` (same `{uid}_background.png` path — overwrites = becomes new canvas).
- Cutout written to `object_cutout_path(..., object_id)` — never overwrites a prior object's cutout.
- `object_id` included in INFO log and returned in `InpaintMaskResponse`.

**New `GET /images/{uid}/objects` (lines ~449–496):**
- Returns `ObjectListResponse` with base64 thumbnails, bounds, and `has_3d` per object.
- Uses `list_object_ids` + `resolve_object_cutout_path` + `_extract_cutout_bounds_from_png_bytes`.
- Per-object loop wrapped in try/except; missing cutouts skip with WARNING.
- Two TODOs: (1) no 404 for unknown UID (mirrors existing `/cache` behavior, MVP); (2) blocking I/O in async — acceptable for MVP session sizes.
- Placed before `/{uid}/cache` to avoid FastAPI path shadowing.

**`delete_session` DELETE `/images/{uid}` (lines ~393–419):**
- Calls `list_object_ids(storage_dir, uid)` **before** any deletions.
- Deletes all `{uid}_{oid}_cutout.png` via `object_cutout_path`.
- Deletes all `{uid}_{oid}.glb` via `object_glb_path`.
- Legacy `{uid}_cutout.png` and `{uid}.glb` cleanup kept for old sessions.

**`get_uid_cache_status` GET `/images/{uid}/cache` (lines ~447–488):**
- `has_cutout = bool(list_object_ids(...))` — covers both numbered and legacy.
- `has_3d = any(resolve_object_glb_path(..., oid).exists() for oid in obj_ids)` — covers legacy via fallback.
- `cutout_bounds` derived from latest object (`max(obj_ids)`).

**`get_cutout` GET `/images/{uid}/cutout` (lines ~503–522):**
- Now serves latest object via `resolve_object_cutout_path(..., max(obj_ids))` with legacy fallback.

---

### `fastApi-app/api/model_3d.py` (renamed from `objects.py`)

**Renamed:** `fastApi-app/api/objects.py` → `fastApi-app/api/model_3d.py`.

**URL prefix changed:** `/objects` → `/3d`. Tag `"objects"` → `"3d"`.

**`Test3DRequest` (lines 28–38):** Added `object_id: int = 0` field (`ge=0`).

**`generate_test_3d` POST `/3d/test-3d` (lines ~43–115):**
- Reads cutout via `resolve_object_cutout_path(get_image_storage_dir(), uid, object_id)`.
- Writes GLB to `object_glb_path(glb_dir, uid, object_id)` → `{uid}_{object_id}.glb`.

**New route `GET /3d/{uid}/{object_id}` (lines ~129–145):**
- Uses `resolve_object_glb_path` (handles legacy fallback for id 0).
- Placed **before** `GET /3d/{uid}` so FastAPI matches the two-segment path first.

**Legacy `GET /3d/{uid}` (lines ~147–160):**
- Updated to use `resolve_object_glb_path(..., uid, 0)` instead of hardcoded `{uid}.glb`.

---

### `fastApi-app/main.py`

- Line 10: `from api.objects import router as objects_router` → `from api.model_3d import router as model_3d_router`
- Line 53: `app.include_router(objects_router)` → `app.include_router(model_3d_router)`

---

### `react-front/src/types/api.ts`

**`InpaintMaskResponse` (lines 54–56):** Changed from `type` alias to `interface` extending `ClickResultResponse`, added `object_id: number`.

**New `ObjectInfo` interface (lines 78–84):** `object_id`, `cutout_b64`, `format`, `cutout_bounds?`, `has_3d`.

**New `ObjectListResponse` interface (lines 86–89):** `uid`, `objects: ObjectInfo[]`.

---

### `react-front/src/api/images.ts`

**`generate3DModel` (lines 52–67):** Added `objectId: number` param; sends `object_id: objectId` in body (snake_case); URL changed to `/3d/test-3d`.

**`fetchCached3DModel` (lines 127–135):** Added `objectId: number` param; URL changed from `/objects/${uid}` to `/3d/${uid}/${objectId}`.

**New `getSessionObjects` (lines 137–140):** `GET /images/${uid}/objects` → `ObjectListResponse`.

---

### `react-front/src/components/layout/MainPage.tsx`

**New `CutoutObject` interface (lines 50–56):**
```typescript
{ objectId: number; cutoutSrc: string; cutoutAlphaBounds: CutoutAlphaBounds | null;
  normalizedClickPos: ClickPosition | null; glbData: ArrayBuffer | null; }
```

**Removed state:** `cutoutSrc`, `cutoutAlphaBounds`, `sessionLocked`, `glbData` scalars.

**New state (lines 170–174):** `objects: CutoutObject[]`, `activeObjectId: number | null`, `isAddingObject: boolean`, `objectPanelCollapsed: boolean`.

**Derived active-object values (lines 210–213):** `activeObject`, `cutoutSrc`, `cutoutAlphaBounds`, `glbData` derived from `objects.find(o => o.objectId === activeObjectId)`. All downstream hooks using these continue to work — the derivation happens before all callbacks/effects.

**`resetWorkspaceState` (lines 184–207):** Replaced removed state setters with `setObjects([])`, `setActiveObjectId(null)`, `setIsAddingObject(false)`.

**`handleSessionSelect` (lines 272–306):** Now calls `getSessionObjects(uid)` when `has_cutout` is true; maps `ObjectInfo[]` to `CutoutObject[]`; sets `activeObjectId` to last object's id; sets `showCutout(true)`.

**`handleMaskSelected` (lines 380–417):** Builds a `CutoutObject` from the inpaint result (captures current `normalizedClickPos` into the object), appends to `objects[]`, sets `activeObjectId`, updates `backgroundSrc` to new background. `isAddingObject` set to false.

**New `handleAddObject` (lines 708–715):** Sets `isAddingObject=true`, clears click positions and toggles.

**New `handleSelectObject` (lines 717–726):** Sets `activeObjectId`, clears add mode, resets `cutoutOffset`, sets `showCutout=true`.

**`handleToggle3D` (lines 419–461):**
- Guards on `activeObjectId === null`.
- Snapshots `targetObjectId` before any `await` to avoid stale-closure race (user could switch objects during generation).
- Stores `glbData` in `objects` array via `setObjects(prev => prev.map(...))`.
- Only calls `setShow3D(true)` if `activeObjectId` still matches `targetObjectId` after the await.

**New `handleToggleObjectPanel` (lines 728–730):** `useCallback` wrapper for `setObjectPanelCollapsed` — avoids inline arrow on ObjectPanel prop.

**`clickEnabled` (line 742):** `Boolean(imageId && (!backgroundSrc || isAddingObject))` — allows clicking before any background (first object), or explicitly during add mode.

**`sessionStatus` (lines 743–755):** Now shows `"Adding object"` and `"N object(s) removed"` states.

**Image frame render condition (lines ~827–878):** Shows `UploadFrame` when `!backgroundSrc || isAddingObject`. When `isAddingObject`, `imageSrc = backgroundSrc` so the user clicks on the latest background to segment the next object.

**`Model3DFrame` (line ~871):** `clickNormalizedPos={activeObject?.normalizedClickPos ?? null}` — uses per-object stored click, not the current scalar.

**Control dashboard condition (line ~881):** `backgroundSrc && !isAddingObject && objects.length > 0`.

**Object-list switch buttons (lines ~906–919):** `disabled={isInpainting || isGenerating3D}` — prevents switching active objects during async operations.

**Cut Out button disabled (line ~935):** `(!isAddingObject && !!backgroundSrc)` replaces old `sessionLocked`.

**ObjectPanel mounted (lines ~884–895):** Inside `main-frame-container`, alongside image frame, when `imageId && objects.length > 0`.

---

### `react-front/src/style.css`

**`main-frame-container` (lines ~195–202):** Added `gap: var(--gap-sm); align-items: stretch`. Replaced `> * { width: 100%; }` with `.main-frame-image-area { flex: 1; min-width: 0; }` so the panel doesn't squish the image.

**New Object Panel CSS (~130 lines, before `@media` block):**

| Selector | Purpose |
|---|---|
| `.object-panel-container` | Outer flex row, `flex-shrink: 0` |
| `.object-panel-side` | 28px always-visible column (toggle + add button) |
| `.object-panel-toggle` | Collapse/expand arrow button; fills remaining height in side column |
| `.object-panel-add-side` | Always-visible `+` button in side column; `is-active` when `isAddingObject` |
| `.object-panel-body` | 150px expandable panel; collapses via `width: 0; opacity: 0; pointer-events: none` |
| `.object-panel-body.is-collapsed` | Collapse transition |
| `.object-panel-label` | "Objects" label |
| `.object-panel-list` | Scrollable thumbnail column |
| `.object-thumbnail-btn` | Square thumbnail; checkerboard bg (same stacked-gradient pattern as mask previews); accent border when `.is-active` |
| `.object-thumbnail-img` | `object-fit: contain` |

**Mobile media query addition (`@media (max-width: 768px)`):** `.object-panel-body { display: none }` — hides expanded panel on narrow screens; side column with `+` button stays visible.

---

## Key Architecture Invariants

- **`mask_cache.py` unchanged** — candidate files (`{uid}_mask_{N}_…`) are temporary and scoped to one segmentation; the `_mask_` prefix means `list_object_ids` never matches them.
- **`process_click_on_image` unchanged** — the legacy `/click` endpoint still reads the original upload directly; it is not in the progressive-removal path.
- **Background always overwrites** — `{uid}_background.png` is the single cumulative canvas; each inpaint overwrites it so the next segmentation starts from the cleaned state.
- **Cutouts never overwrite** — `{uid}_{object_id}_cutout.png` is numbered; prior objects survive.
- **`sessionLocked` removed entirely** — its role is replaced by `(!isAddingObject && !!backgroundSrc)` in the Cut Out button guard and `clickEnabled`.
