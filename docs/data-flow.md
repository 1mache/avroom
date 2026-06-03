# Data Flow

Main user path is now split so mask choice remains subjective and user-controlled.

```mermaid
sequenceDiagram
    actor User
    participant UI as "React MainPage"
    participant API as "FastAPI /images"
    participant Segmentor as "ObjectSegmentor"
    participant Cache as "mask candidate cache"
    participant Inpainter as "BackgroundInpainter"

    User->>UI: choose file + Upload
    UI->>API: POST /images/upload
    API-->>UI: image_id

    User->>UI: click object point + Cut Out
    UI->>API: POST /images/segment {image_id,x,y}
    API->>Segmentor: get_mask_for_object_at_position(...)
    Segmentor-->>API: refined masks + cutouts
    API->>Cache: save .npy masks + PNG cutouts
    API-->>UI: SegmentResponse(masks[])

    UI-->>User: mask picker modal
    User->>UI: choose cutout option
    UI->>API: POST /images/inpaint {image_id,mask_id}
    API->>Cache: load selected refined mask
    API->>API: load_canvas_bytes (background if exists, else original)
    API->>Inpainter: cut_mask_from_image(canvas, selected_mask)
    Inpainter-->>API: inpainted background
    API-->>UI: InpaintMaskResponse (background_b64 + cutout_b64 + object_id)
    UI-->>User: updated background + ObjectPanel with new object thumbnail
```

## Frontend

- `UploadFrame` converts display click into natural image pixels. When `isAddingObject` is true, it shows the latest background instead of the original upload.
- `MainPage.handleCutOut` calls `segmentImage(...)` and opens `MaskPickerModal`.
- `MaskPickerModal` shows returned cutout previews, not raw masks.
- `MainPage.handleMaskSelected` calls `inpaintMask(...)`, builds a new `CutoutObject` from the response (including `object_id`), and appends it to `objects[]`. `backgroundSrc` is updated to the new background. The active-object derived values (`cutoutSrc`, `cutoutAlphaBounds`, `glbData`) update automatically.
- `ObjectPanel` renders alongside the image frame when `objects.length > 0`. The `+` button in the panel side column enters add-object mode.

## Backend

- `POST /images/segment` validates click, runs `ObjectSegmentor`, caches each refined mask and cutout.
- `POST /images/inpaint` loads selected refined mask, runs `BackgroundInpainter`, saves final background/cutout, then deletes temporary candidates.
- `POST /images/click` remains as legacy one-step endpoint but normal UI no longer uses it.

## Storage

Runtime files under `fastApi-app/tmp/images/`:

| Pattern | Meaning |
|---|---|
| `{uid}.{ext}` | Original upload. |
| `{uid}_mask_{mask_id}_refined.npy` | Temporary selected-mask model input. |
| `{uid}_mask_{mask_id}_cutout.png` | Temporary user-facing candidate preview. |
| `{uid}_background.png` | Cumulative inpainted canvas (overwritten on each inpaint). |
| `{uid}_{object_id}_cutout.png` | Per-object cutout (numbered, never overwritten). |
| `{uid}_cutout.png` | Legacy flat cutout (sessions before per-object numbering). |
