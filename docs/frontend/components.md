# Components

There are five real components, all functional with hooks.

## `MainPage`

[`react-front/src/components/layout/MainPage.tsx`](../../react-front/src/components/layout/MainPage.tsx)

The screen-level orchestrator. Owns all state, all callbacks, and renders a `SessionPicker`, one `UploadFrame`, two `ResultFrame`s (Background and Cutout), a `Model3DFrame`, and action buttons.

**Responsibilities:**

- Hold the picked file, the preview object URL, the `image_id` from the backend, the click positions (display + natural + normalized), the result data URLs, and 3D model bytes.
- Talk to the backend via `uploadImage` / `clickImage` / `getSessions` / `getUidCacheStatus` from [`api/images.ts`](../../react-front/src/api/images.ts).
- Restore prior session state via `handleSessionSelect` when the user picks a session from `SessionPicker`.
- Track loading flags (`isUploading`, `isProcessing`, `isGenerating3D`) and show error text under the buttons.
- Revoke object URLs on unmount and on file replacement to avoid leaks.

**Render tree:**

```mermaid
flowchart TD
    Page["div.page"]
    Header["header.page-header"]
    SessionPicker["SessionPicker"]
    Top["section.top-frame-section"]
    Bottom["section.bottom-frame-section"]
    Upload["UploadFrame"]
    Bg["ResultFrame (Background)"]
    Co["ResultFrame (Cutout)"]
    Actions["div.action-column<br/>Upload + Run buttons"]
    Model3D["Model3DFrame"]

    Page --> Header
    Page --> SessionPicker
    Page --> Top
    Page --> Bottom
    Top --> Upload
    Bottom --> Bg
    Bottom --> Actions
    Bottom --> Co
    Page --> Model3D
```

**Buttons:**

- **Upload** — disabled if `isUploading || !uploadedFile`. On click runs `handleUpload`.
- **Run** — disabled if `isProcessing || !imageId || !clickPosition`. On click runs `handleRun`.

See [user-flow.md](user-flow.md) for what each callback does.

## `UploadFrame`

[`react-front/src/components/widgets/UploadFrame.tsx`](../../react-front/src/components/widgets/UploadFrame.tsx)

The upload widget. Two visual modes:

1. **Empty** — a placeholder button with an upload icon. Clicking it (or pressing Enter) opens the hidden `<input type="file">`.
2. **Filled** — shows the image and overlays a red dot at the last click position.

**Props:**

| Prop | Type | Notes |
|---|---|---|
| `imageSrc` | `string \| null` | Object URL produced by `MainPage`. |
| `clickPosition` | `{ x: number; y: number } \| null` | Display-space dot location. |
| `onFileSelected` | `(file: File) => void` | Called when the user picks a file. |
| `onImageClick` | `(displayPos, naturalPos) => void` | Called when the user clicks the image. |
| `disabled` | `boolean` | Disables both file picking and click capture. |

**Coordinate math:**

```43:62:react-front/src/components/widgets/UploadFrame.tsx
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    
    const img = imageRef.current;
    if (img) {
      const imgRect = img.getBoundingClientRect();
      const clickXOnImg = event.clientX - imgRect.left;
      const clickYOnImg = event.clientY - imgRect.top;
      
      const naturalPos = {
        x: Math.round((clickXOnImg / imgRect.width) * img.naturalWidth),
        y: Math.round((clickYOnImg / imgRect.height) * img.naturalHeight),
      };
      
      onImageClick({ x, y }, naturalPos);
    } else {
      onImageClick({ x, y }, { x, y });
    }
```

The container click handler emits **both** positions:

- **Display position** — for the visual dot overlay (CSS `left` / `top` in container pixels).
- **Natural position** — `clickXOnImg / imgRect.width * img.naturalWidth` (and same for Y), rounded to integers — this is what gets sent to the backend so segmentation works in real image pixels regardless of how the image is rendered.

If `imageRef` is somehow null, the natural position falls back to display position.

## `ResultFrame`

[`react-front/src/components/widgets/ResultFrame.tsx`](../../react-front/src/components/widgets/ResultFrame.tsx)

A passive display component. Title at the top, then either an `<img>` if `imageSrc` is non-null, or a placeholder.

```1:20:react-front/src/components/widgets/ResultFrame.tsx
import React from "react";

export interface ResultFrameProps {
  title: string;
  imageSrc?: string | null;
}

export const ResultFrame: React.FC<ResultFrameProps> = ({ title, imageSrc }) => {
  return (
    <div className="frame result-frame">
      <div className="frame-title">{title}</div>
      {imageSrc ? (
        <img src={imageSrc} alt={title} className="frame-image" />
      ) : (
        <div className="frame-placeholder">Result will appear here</div>
      )}
    </div>
  );
};
```

`MainPage` renders two of these, one for Background and one for Cutout, fed by data URLs assembled from the base64 fields of `ClickResultResponse`.

## `SessionPicker`

[`react-front/src/components/widgets/SessionPicker.tsx`](../../react-front/src/components/widgets/SessionPicker.tsx)

Displays the list of past sessions so the user can restore the app to a prior state.

**Props:**

| Prop | Type | Notes |
|---|---|---|
| `onSessionSelect` | `(uid: string) => void` | Called when the user clicks a session entry. |

**Internal state:**

```typescript
interface SessionMeta {
  uid: string;
  hasResults: boolean;
}
sessions: SessionMeta[] | null
```

On mount the component calls `getSessions()` to get all UIDs, then fans out `getUidCacheStatus(uid)` in parallel for each, setting `hasResults = has_background || has_cutout`. Sessions without results are still shown (the user can re-run segmentation).

**Session restore in `MainPage.handleSessionSelect`** ([`MainPage.tsx`](../../react-front/src/components/layout/MainPage.tsx) lines 65–84):

1. Sets `imageId` to the selected UID.
2. Clears `uploadedFile` and all click positions.
3. Points `uploadedImageUrl` at `GET /images/{uid}/original`.
4. Calls `getUidCacheStatus(uid)` — if background/cutout exist, sets `backgroundSrc` / `cutoutSrc` to the corresponding `GET /images/{uid}/background|cutout` URLs so results render immediately.

## `Model3DFrame`

[`react-front/src/components/widgets/Model3DFrame.tsx`](../../react-front/src/components/widgets/Model3DFrame.tsx)

Three.js viewer for the generated GLB model. Renders a canvas with a three-point lighting rig and `OrbitControls`. A `ResizeObserver` keeps the canvas sized to its container.

**Props:**

| Prop | Type | Notes |
|---|---|---|
| `glbData` | `ArrayBuffer \| null` | Raw GLB bytes from `generate3DModel`. Null renders a placeholder. |
| `backgroundImage` | `string \| null` | Optional background image URL (unused visually, reserved). |
| `clickNormalizedPos` | `NormalizedPos \| null` | Normalized `(x, y)` used to offset the camera view toward the clicked object. |
