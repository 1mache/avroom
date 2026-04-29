# Backend Request Lifecycle

Two endpoints, two flows. Both go through `fastApi-app/api/routes.py`.

## Upload flow

```mermaid
sequenceDiagram
    participant Client
    participant Router as "api/routes.py<br/>upload_image"
    participant Settings as "settings.py"
    participant Disk as "fastApi-app/images/"

    Client->>Router: POST /images/upload (multipart file)
    Router->>Settings: get_image_storage_dir()
    Settings-->>Router: Path
    Router->>Disk: mkdir -p
    Router->>Router: image_id = uuid.uuid4()
    Router->>Router: pick suffix from filename or .png
    Router->>Router: file.read()
    Router->>Disk: write {image_id}{suffix}
    Router-->>Client: ImageUploadResponse
```

Code: [`fastApi-app/api/routes.py`](../../fastApi-app/api/routes.py) lines 24–54.

## Click flow

```mermaid
sequenceDiagram
    participant Client
    participant Router as "api/routes.py<br/>handle_click"
    participant Settings as "settings.py"
    participant Core as "core/image_processing.py"
    participant Disk as "fastApi-app/images/"
    participant AI as "ObjectRemover"

    Client->>Router: POST /images/click (ClickRequest)
    Router->>Settings: get_image_storage_dir()
    Router->>Core: process_click_on_image(image_id, x, y, options)
    Core->>Disk: read image bytes via get_image_path glob
    Core->>Core: PIL bounds check + debug PNG to images/tmp/
    Core->>Core: segment_at_click(bytes, x, y)
    Core->>Core: lazy import ObjectRemover
    Core->>AI: remover.remove_object(image_path, x, y, image_bytes)
    AI-->>Core: (background_bgr, cutout_bgra)
    Core->>Core: cv2.imencode each as PNG
    Core-->>Router: (bg_bytes, cutout_bytes, "png")
    Router->>Router: base64 each
    Router-->>Client: ClickResultResponse
```

## Per-step file:line references

| Step | File | Lines |
|---|---|---|
| Resolve storage dir | [`fastApi-app/api/routes.py`](../../fastApi-app/api/routes.py) | 35, 66 |
| Locate file by `image_id.*` | [`fastApi-app/core/image_processing.py`](../../fastApi-app/core/image_processing.py) | 53–59 |
| Load bytes | [`fastApi-app/core/image_processing.py`](../../fastApi-app/core/image_processing.py) | 62–70 |
| PIL open + bounds check | [`fastApi-app/core/image_processing.py`](../../fastApi-app/core/image_processing.py) | 125–145 |
| Debug PNG (`tmp/{id}_debug.png`) | [`fastApi-app/core/image_processing.py`](../../fastApi-app/core/image_processing.py) | 32–50, 141 |
| Lazy import pipeline | [`fastApi-app/core/image_processing.py`](../../fastApi-app/core/image_processing.py) | 19–29 |
| Call `ObjectRemover.remove_object` | [`fastApi-app/core/image_processing.py`](../../fastApi-app/core/image_processing.py) | 89–96 |
| `cv2.imencode` PNG | [`fastApi-app/core/image_processing.py`](../../fastApi-app/core/image_processing.py) | 98–106 |
| Exception → HTTP status | [`fastApi-app/api/routes.py`](../../fastApi-app/api/routes.py) | 76–84 |
| Base64 encode | [`fastApi-app/api/routes.py`](../../fastApi-app/api/routes.py) | 86–87 |
| Build response | [`fastApi-app/api/routes.py`](../../fastApi-app/api/routes.py) | 89–94 |

## Synchronous, no concurrency

Every request blocks until `ObjectRemover.remove_object` returns. With a CPU-only setup this is many seconds. There is no queue, no worker pool, no streaming progress channel — the response only comes back after the full pipeline is done.

If you ever need parallel requests, note that the AI pipeline caches the SAM predictor, LaMa, the SD pipe and HF depth pipelines behind module-level `functools.lru_cache` factories — one shared instance of each per process. Serializing access to those (especially the SD pipeline) is left to the caller.
