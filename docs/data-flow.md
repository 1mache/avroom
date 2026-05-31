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
    API->>Inpainter: cut_mask_from_image(...)
    Inpainter-->>API: inpainted background
    API-->>UI: background_b64 + selected cutout_b64
    UI-->>User: final background + optional cutout overlay
```

## Frontend

- `UploadFrame` still converts display click into natural image pixels.
- `MainPage.handleCutOut` calls `segmentImage(...)` and opens `MaskPickerModal`.
- `MaskPickerModal` shows returned cutout previews, not raw masks.
- `MainPage.handleMaskSelected` calls `inpaintMask(...)` and reuses existing final result state: `backgroundSrc`, `cutoutSrc`, and `cutoutAlphaBounds`.

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
| `{uid}_background.png` | Final inpainted background. |
| `{uid}_cutout.png` | Final selected cutout. |
