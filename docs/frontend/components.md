# Components

Current frontend has five important screen components plus one data sidebar widget.

## `MainPage`

[`react-front/src/components/layout/MainPage.tsx`](../../react-front/src/components/layout/MainPage.tsx)

Screen orchestrator. Owns upload flow, segmentation mask choice, selected-mask inpainting, session restore flow, draggable cutout overlay, and optional 3D overlay.

### Responsibilities

- Hold upload/session/result state.
- Hold temporary `maskOptions` state while user chooses segmentation candidate.
- Convert backend `cutout_bounds` metadata into local drag bounds.
- Measure rendered result viewport and derive the exact contained image rect used by `object-fit: contain`.
- Translate pointer movement from CSS pixels into natural-image pixels.
- Clamp cutout movement by visible object bounds, not by full transparent PNG extent.
- Restore enough metadata from `/images/{uid}/cache` so old sessions can drag immediately without re-running segmentation.

### Result-stage structure

When a background exists, `MainPage` no longer renders a plain `<img>`. It renders a measured stage:

```tsx
<div className="frame upload-frame result-main-frame">
  <div ref={resultStageRef} className="image-container result-image-stage">
    <img src={backgroundSrc} className="frame-image" onLoad={handleBackgroundLoad} />
    {showCutout ? <img src={cutoutSrc} className="cutout-overlay" ... /> : null}
    {show3D ? <Model3DFrame className="overlay-absolute model-overlay" ... /> : null}
  </div>
</div>
```

Non-trivial point: `cutout-overlay` and `Model3DFrame` are aligned to the inner `image-container`, not the outer `.frame`. This avoids hard-coded padding math and keeps overlays aligned with the real visible image box.

### Drag model

Drag is implemented in three spaces:

1. **Natural image space**
   `cutoutOffset` and `cutoutAlphaBounds` live here. This is the source of truth.
2. **Rendered image space**
   `renderedBackgroundRect` describes where the browser actually painted the background image inside the stage.
3. **Pointer/screen space**
   `PointerEvent.clientX/clientY` arrive here.

Conversion path during drag:

1. User presses cutout image.
2. `handleCutoutPointerDown` stores pointer id, starting mouse coordinates, and starting `cutoutOffset`.
3. Window-level `pointermove` listener computes screen delta.
4. Delta is divided by `scaleX/scaleY` derived from `renderedBackgroundRect / backgroundNaturalSize`.
5. Result becomes a natural-image delta.
6. `clampCutoutOffset` clamps that natural offset using `cutoutAlphaBounds`.
7. Render path scales natural offset back into CSS pixels for `left/top`.

Why window-level listeners:

- Native image pointer flow can stop delivering events once pointer leaves image box.
- Global listeners let drag continue smoothly even when user outruns overlay edge.
- Refs carry latest geometry into those listeners without forcing re-subscription on every move.

## `UploadFrame`

[`react-front/src/components/widgets/UploadFrame.tsx`](../../react-front/src/components/widgets/UploadFrame.tsx)

Still responsible only for upload preview and point selection. No drag logic lives here.

Important split:

- `UploadFrame` handles **where user clicked on original image**.
- `MainPage` handles **how returned cutout can later move on top of processed background**.

## `MaskPickerModal`

[`react-front/src/components/widgets/MaskPickerModal.tsx`](../../react-front/src/components/widgets/MaskPickerModal.tsx)

Renders segmentation candidates after `POST /images/segment`.

- Shows cutout previews, not black-white masks.
- Uses horizontal grid/scroll so several candidates can be compared.
- Locks close/select buttons while selected mask is being inpainted.
- Emits only `mask_id`; `MainPage` owns API call and final result state.

## `SessionPicker`

[`react-front/src/components/widgets/SessionPicker.tsx`](../../react-front/src/components/widgets/SessionPicker.tsx)

No structural change, but session restore now matters more:

- `MainPage.handleSessionSelect(...)` restores `backgroundSrc`.
- It also restores `cutoutSrc`.
- It now also restores `cutoutAlphaBounds` from `GET /images/{uid}/cache`.

That extra metadata is what lets an old cutout drag with correct clamping even though the original segmentation request is long gone.

## `Model3DFrame`

[`react-front/src/components/widgets/Model3DFrame.tsx`](../../react-front/src/components/widgets/Model3DFrame.tsx)

No behavioral change, but z-index contract changed:

- `.model-overlay` sits below `.cutout-overlay`.
- This lets cutout stay visually draggable above 3D overlay if both are enabled.

## CSS roles

[`react-front/src/style.css`](../../react-front/src/style.css)

New classes tied to drag feature:

- `body.cutout-dragging`: global `grabbing` cursor during active drag.
- `.result-image-stage`: isolated overlay stage that owns measurement and stacking context.
- `.cutout-overlay`: absolute positioned draggable image with `touch-action: none`.
- `.model-overlay`: z-index layer for 3D viewer.
- `.overlay-absolute`: now fills stage exactly. Old fixed `14px` inset was removed because stage already sits inside padded frame.
