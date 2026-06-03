# Backend Request Lifecycle

Three image flows go through `fastApi-app/api/routes.py`.

## Upload Flow

```mermaid
sequenceDiagram
    participant Client
    participant Router as "api/routes.py"
    participant Settings as "settings.py"
    participant Disk as "tmp/images"

    Client->>Router: POST /images/upload
    Router->>Settings: get_image_storage_dir()
    Router->>Disk: write {image_id}.{ext}
    Router-->>Client: ImageUploadResponse
```

## Segment Flow

```mermaid
sequenceDiagram
    participant Client
    participant Router as "api/routes.py"
    participant Core as "core/image_processing.py"
    participant Cache as "core/mask_cache.py"
    participant AI as "ObjectSegmentor"

    Client->>Router: POST /images/segment {image_id,x,y}
    Router->>Core: segment_candidates_on_image(...)
    Core->>Core: load image + validate natural click
    Core->>Cache: delete stale candidates
    Core->>AI: get_mask_for_object_at_position(...)
    AI-->>Core: (refined_mask, cutout_bgra)[]
    Core->>Cache: save .npy masks + PNG cutouts
    Router-->>Client: SegmentResponse(masks[])
```

## Inpaint Flow

```mermaid
sequenceDiagram
    participant Client
    participant Router as "api/routes.py"
    participant Core as "core/image_processing.py"
    participant Cache as "core/mask_cache.py"
    participant AI as "BackgroundInpainter"
    participant Disk as "tmp/images"

    Client->>Router: POST /images/inpaint {image_id,mask_id}
    Router->>Core: inpaint_selected_mask_on_image(...)
    Core->>Core: load_canvas_bytes (background if exists, else original)
    Core->>Cache: load selected refined mask + cutout
    Core->>AI: cut_mask_from_image(canvas, refined_mask)
    AI-->>Core: background_bgr
    Router->>Router: next_object_id(storage_dir, uid)
    Router->>Disk: write {uid}_background.png (new canvas)
    Router->>Disk: write {uid}_{object_id}_cutout.png
    Router->>Cache: delete temporary candidates
    Router-->>Client: InpaintMaskResponse (includes object_id)
```

## Cache Rules

- Candidate cache exists only between segmentation response and user selection.
- New segmentation for same image deletes older candidates first.
- Segmentation reads from the current canvas (`{uid}_background.png` if present, original otherwise) — each new object is cut from the already-cleaned room image.
- Successful inpaint writes the new background to `{uid}_background.png` (overwrites — becomes the canvas for the next object) and the cutout to `{uid}_{object_id}_cutout.png` (numbered — prior objects are never overwritten).
- Successful inpaint deletes every `{uid}_mask_*` temporary file.

## Synchronous Model

Endpoints remain synchronous. Segmentation returns only after all mask candidates are ready; inpainting returns only after selected background is generated. There is no queue, progress stream, or worker pool.
