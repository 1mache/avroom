# State and Types

The frontend still keeps all screen state inside [`react-front/src/components/layout/MainPage.tsx`](../../react-front/src/components/layout/MainPage.tsx). Dragging the cutout added more geometry state and a few refs used only by pointer listeners.

## `MainPage` state

| Variable | Type | Set by | Used for |
|---|---|---|---|
| `uploadedFile` | `File \| null` | `handleFileSelected` | Source for `URL.createObjectURL` and multipart upload. |
| `uploadedImageUrl` | `string \| null` | `handleFileSelected` / `handleSessionSelect` | `<img src>` for live preview or restored original image. |
| `imageId` | `string \| null` | upload response / session restore | Backend handle for cutout and 3D requests. |
| `clickPosition` | `{ x; y } \| null` | `handleImageClick` | Display-space dot overlay in `UploadFrame`. |
| `naturalClickPos` | `{ x; y } \| null` | `handleImageClick` | Natural-image click coordinate sent to backend. |
| `normalizedClickPos` | `{ x; y } \| null` | `handleImageClick` | Camera bias input for `Model3DFrame`. |
| `backgroundSrc` | `string \| null` | `handleMaskSelected` / session restore | Latest cumulative background URL (always shows the most recent inpainted state). |
| `backgroundNaturalSize` | `{ width; height } \| null` | `handleBackgroundLoad` | Natural size of background image. Used to convert drag between CSS pixels and image pixels. |
| `resultStageSize` | `{ width; height } \| null` | `measureResultStage` | Actual size of rendered result viewport. |
| `cutoutOffset` | `{ x; y }` | pointer drag lifecycle | Current cutout translation in natural-image pixels. Resets to `{0,0}` when active object changes. |
| `objects` | `CutoutObject[]` | `handleMaskSelected` / session restore | All inpainted objects for this session, in creation order. |
| `activeObjectId` | `number \| null` | `handleMaskSelected` / `handleSelectObject` / session restore | Which object's cutout and 3D the bottom checkboxes target. |
| `isAddingObject` | `boolean` | `handleAddObject` / `handleMaskSelected` | When `true`, `UploadFrame` re-appears over the latest background so the user can click a new object. |
| `objectPanelCollapsed` | `boolean` | `handleToggleObjectPanel` | Collapse state of the `ObjectPanel` right-side rail. |
| `showCutout` | `boolean` | dashboard toggle | Whether the active object's cutout overlay is rendered. |
| `show3D` | `boolean` | dashboard toggle | Whether the active object's 3D overlay is rendered. |
| `maskOptions` | `SegmentMaskOption[]` | `segmentImage` / reset / modal close | Candidate cutouts shown in mask picker modal. |
| `selectedMaskId` | `string \| null` | mask picker selection | Busy-state marker for selected candidate. |
| `isDraggingCutout` | `boolean` | pointer drag lifecycle | Keeps window-level pointer listeners alive and sets drag cursor. |
| `isUploading` | `boolean` | `handleUpload` | Upload button busy state. |
| `isProcessing` | `boolean` | `handleCutOut` | Segmentation busy state. |
| `isInpainting` | `boolean` | `handleMaskSelected` | Selected-mask inpainting busy state. |
| `isGenerating3D` | `boolean` | `handleToggle3D` | 3D toggle busy/disabled state. |
| `isDeleting` | `boolean` | `handleDeleteSession` | Delete button busy state. |
| `deleteConfirming` | `boolean` | `handleDeleteSession` | Two-step confirm state before session delete. |
| `error` | `string \| null` | async handlers | Error modal contents. |
| `sessionName` | `string` | upload / session restore / name input | Current value of editable session name field. Prefilled with uid on upload; prefilled with `status.name ?? uid` on session restore. |
| `sessionsRefreshKey` | `number` | upload / name save | Incremented after upload or after name saved. Passed as `refreshKey` prop to `SessionPicker` to trigger re-fetch. |

### Derived active-object values

`cutoutSrc`, `cutoutAlphaBounds`, and `glbData` are **not** state — they are derived constants computed at render time from the active `CutoutObject`:

```ts
const activeObject = objects.find(o => o.objectId === activeObjectId) ?? null;
const cutoutSrc = activeObject?.cutoutSrc ?? null;
const cutoutAlphaBounds = activeObject?.cutoutAlphaBounds ?? null;
const glbData = activeObject?.glbData ?? null;
```

These are placed after all state declarations and before hooks so every effect and callback sees the correct active-object values.

## Drag refs

These refs are part of drag implementation but are intentionally not state:

| Ref | Type | Role |
|---|---|---|
| `resultStageRef` | `HTMLDivElement \| null` | DOM node measured by `ResizeObserver`. |
| `dragStateRef` | `DragState \| null` | Pointer id and drag start values. Avoids re-rendering on every mouse move. |
| `backgroundNaturalSizeRef` | `Size \| null` | Latest natural image size for window-level pointer handlers. |
| `cutoutAlphaBoundsRef` | `CutoutAlphaBounds \| null` | Latest visible-object bounds for window-level pointer handlers. |
| `renderedBackgroundRectRef` | contained image rect \| `null` | Latest contained `object-fit: contain` rect for window-level pointer handlers. |

## Geometry helpers

`MainPage` defines several private helper types/functions:

- `Size`: width/height pair in pixels.
- `CutoutAlphaBounds`: visible-object box inside full cutout PNG. `right` and `bottom` are exclusive.
- `DragState`: pointer id plus mouse start position and cutout start offset.
- `CutoutObject`: per-object record stored in the `objects` array. Fields: `objectId: number`, `cutoutSrc: string`, `cutoutAlphaBounds: CutoutAlphaBounds | null`, `normalizedClickPos: ClickPosition | null` (for 3D camera bias; `null` on session restore), `glbData: ArrayBuffer | null`.
- `getContainedImageRect(...)`: reproduces browser `object-fit: contain` placement so overlays line up with the visible image area instead of whole frame.
- `clampCutoutOffset(...)`: clamps drag using `cutoutAlphaBounds`, not raw PNG size.
- `toCutoutAlphaBounds(...)`: converts backend snake_case API fields into local camelCase state.

## State invariants

- Picking a new file resets click state, result state, `objects[]`, `activeObjectId`, `isAddingObject`, mask options, drag state, and any cached bounds. User must upload again before Cut Out is available.
- `objects[]` reset also fires on session delete and session switch.
- Session restore may load `cutoutAlphaBounds` before background image metrics exist. `cutoutOffset` is therefore re-clamped when either bounds or background size changes.
- Switching active object via `handleSelectObject` resets `cutoutOffset` to `{0,0}` and sets `showCutout=true`.
- `cutoutOffset` always lives in natural-image pixels. Pointer movement is converted from screen pixels into natural pixels during drag.
- If backend does not provide `cutout_bounds`, drag still renders, but clamping falls back to full-image bounds.
- Object URL cleanup still happens on replacement and unmount to avoid leaking `blob:` URLs.

## TypeScript API mirror

All API types live in [`react-front/src/types/api.ts`](../../react-front/src/types/api.ts). They mirror backend Pydantic models in [`fastApi-app/schemas/image.py`](../../fastApi-app/schemas/image.py).

```ts
export interface SessionInfo {
  uid: string;
  name: string | null;
}

export interface ClickResultResponse {
  image_id: string;
  background_b64: string;
  cutout_b64: string;
  format: string;
  cutout_bounds?: CutoutBounds | null;
}

export interface SegmentMaskOption {
  mask_id: string;
  cutout_b64: string;
  format: string;
  cutout_bounds?: CutoutBounds | null;
}

export interface SegmentResponse {
  image_id: string;
  masks: SegmentMaskOption[];
}

export interface InpaintMaskRequest {
  image_id: string;
  mask_id: string;
}

export interface InpaintMaskResponse extends ClickResultResponse {
  object_id: number;
}

export interface ObjectInfo {
  object_id: number;
  cutout_b64: string;
  format: string;
  cutout_bounds?: CutoutBounds | null;
  has_3d: boolean;
}

export interface ObjectListResponse {
  uid: string;
  objects: ObjectInfo[];
}

export interface UidCacheStatusResponse {
  uid: string;
  name?: string | null;
  has_background: boolean;
  has_cutout: boolean;
  has_3d: boolean;
  cutout_bounds?: CutoutBounds | null;
}

export interface CutoutBounds {
  left: number;
  top: number;
  right: number;
  bottom: number;
  natural_width: number;
  natural_height: number;
}
```

No codegen exists. Backend schema changes still require manual frontend mirror updates.
