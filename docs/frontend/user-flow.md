# User Flow

Primary flow: pick image → upload → click object → segment → choose mask → inpaint → optional cutout overlay.

```mermaid
sequenceDiagram
    actor User
    participant UF as UploadFrame
    participant MP as MainPage
    participant API as "api/images.ts"
    participant Backend as "FastAPI backend"

    User->>UF: choose file
    UF->>MP: onFileSelected(file)
    User->>MP: click Upload
    MP->>API: uploadImage(file)
    API->>Backend: POST /images/upload
    Backend-->>API: ImageUploadResponse
    API-->>MP: image_id

    User->>UF: click object point
    UF->>MP: display/natural/normalized coords
    User->>MP: click Cut Out
    MP->>API: segmentImage({image_id,x,y})
    API->>Backend: POST /images/segment
    Backend-->>API: SegmentResponse(masks[])
    MP-->>User: MaskPickerModal

    User->>MP: select mask option
    MP->>API: inpaintMask({image_id,mask_id})
    API->>Backend: POST /images/inpaint
    Backend-->>API: InpaintMaskResponse
    API-->>MP: background + selected cutout
    MP-->>User: result stage
```

## Mask Picker

- Modal appears over current UI after segmentation completes.
- Cards show cutout images with original object pixels and transparent background.
- Clicking card starts inpainting.
- Modal cannot close while inpainting is running because backend may remove temporary candidate files after selection.

## Drag Sequence

Drag behavior is unchanged after inpaint: cutout offset lives in natural image pixels, pointer delta converts through rendered background rect, and `cutout_bounds` clamps visible object inside frame.

## Session Restore

Restored sessions still load final `/images/{uid}/background`, `/images/{uid}/cutout`, and bounds from `/images/{uid}/cache`. They do not restore temporary mask candidates.
