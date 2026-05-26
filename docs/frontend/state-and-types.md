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
| `backgroundSrc` | `string \| null` | `clickImage` / session restore | Background result image URL. |
| `cutoutSrc` | `string \| null` | `clickImage` / session restore | Cutout result image URL. |
| `backgroundNaturalSize` | `{ width; height } \| null` | `handleBackgroundLoad` | Natural size of background image. Used to convert drag between CSS pixels and image pixels. |
| `resultStageSize` | `{ width; height } \| null` | `measureResultStage` | Actual size of rendered result viewport. |
| `cutoutAlphaBounds` | `CutoutAlphaBounds \| null` | backend responses | Tight visible-object bounds inside full cutout PNG. |
| `cutoutOffset` | `{ x; y }` | pointer drag lifecycle | Current cutout translation in natural-image pixels. |
| `sessionLocked` | `boolean` | `clickImage` / reset / session restore | Prevents re-clicking source image after segmentation result is active. |
| `showCutout` | `boolean` | dashboard toggle | Whether draggable cutout overlay is rendered. |
| `show3D` | `boolean` | dashboard toggle | Whether 3D overlay is rendered. |
| `isDraggingCutout` | `boolean` | pointer drag lifecycle | Keeps window-level pointer listeners alive and sets drag cursor. |
| `isUploading` | `boolean` | `handleUpload` | Upload button busy state. |
| `isProcessing` | `boolean` | `handleCutOut` | Cut Out button busy state. |
| `isGenerating3D` | `boolean` | `handleToggle3D` | 3D toggle busy/disabled state. |
| `glbData` | `ArrayBuffer \| null` | 3D API responses | Raw GLB bytes for `Model3DFrame`. |
| `error` | `string \| null` | async handlers | Error modal contents. |

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
- `getContainedImageRect(...)`: reproduces browser `object-fit: contain` placement so overlays line up with the visible image area instead of whole frame.
- `clampCutoutOffset(...)`: clamps drag using `cutoutAlphaBounds`, not raw PNG size.
- `toCutoutAlphaBounds(...)`: converts backend snake_case API fields into local camelCase state.

## State invariants

- Picking a new file resets click state, result state, drag state, 3D state, and any cached bounds. User must upload again before Cut Out is available.
- Session restore may load `cutoutAlphaBounds` before background image metrics exist. `cutoutOffset` is therefore re-clamped when either bounds or background size changes.
- `cutoutOffset` always lives in natural-image pixels. Pointer movement is converted from screen pixels into natural pixels during drag.
- If backend does not provide `cutout_bounds`, drag still renders, but clamping falls back to full-image bounds.
- Object URL cleanup still happens on replacement and unmount to avoid leaking `blob:` URLs.

## TypeScript API mirror

All API types live in [`react-front/src/types/api.ts`](../../react-front/src/types/api.ts). They mirror backend Pydantic models in [`fastApi-app/schemas/image.py`](../../fastApi-app/schemas/image.py).

```ts
export interface ClickResultResponse {
  image_id: string;
  background_b64: string;
  cutout_b64: string;
  format: string;
  cutout_bounds?: CutoutBounds | null;
}

export interface UidCacheStatusResponse {
  uid: string;
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
