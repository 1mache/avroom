# End-to-End Data Flow

This document traces a single user interaction — selecting a room image, clicking an object, and seeing the result — across all three tiers.

## Sequence diagram

```mermaid
sequenceDiagram
    actor User
    participant UI as "React SPA<br/>(MainPage / UploadFrame)"
    participant API as "FastAPI<br/>/images and /objects routers"
    participant Disk as "fastApi-app/tmp/images/"
    participant Core as "core.image_processing"
    participant AI as "ObjectRemover<br/>(avroom_object_removal)"

    User->>UI: pick file (<input type="file">)
    UI->>UI: URL.createObjectURL for preview
    User->>UI: click "Upload"
    UI->>API: POST /images/upload (multipart file)
    API->>Disk: write {image_id}.{ext}
    API-->>UI: ImageUploadResponse(image_id, ...)

    User->>UI: click on image
    UI->>UI: scale click to natural pixel coords
    User->>UI: click "Run"
    UI->>API: POST /images/click {image_id, x, y}
    API->>Disk: read {image_id}.* bytes
    API->>Core: process_click_on_image(image_id, x, y)
    Core->>Core: PIL bounds check + debug PNG (point/)
    Core->>AI: ObjectRemover().remove_object(image_bytes, x, y)
    AI->>AI: depth -> adapter -> router -> SAM -> refine -> inpaint -> compose
    AI-->>Core: (background_bgr, cutout_bgra) numpy arrays
    Core->>Core: cv2.imencode each as PNG
    Core-->>API: (background_bytes, cutout_bytes, "png")
    API->>API: base64.b64encode each
    API-->>UI: ClickResultResponse(background_b64, cutout_b64, format)
    UI->>UI: build data:image/png;base64,... for both
    UI-->>User: render Background and Cutout frames
```

## Step-by-step

### 1. File pick (frontend)

- [`react-front/src/components/widgets/UploadFrame.tsx`](../react-front/src/components/widgets/UploadFrame.tsx) lines 22–28 — the hidden `<input type="file">` calls `onFileSelected(file)`.
- [`react-front/src/components/layout/MainPage.tsx`](../react-front/src/components/layout/MainPage.tsx) lines 34–51 — `handleFileSelected` resets all derived state, calls `URL.createObjectURL(file)` for live preview, and revokes any previous object URL.

### 2. Upload (frontend → backend)

- `MainPage.handleUpload` ([`MainPage.tsx`](../react-front/src/components/layout/MainPage.tsx) lines 58–77) calls `uploadImage(file)`.
- `uploadImage` ([`react-front/src/api/images.ts`](../react-front/src/api/images.ts) lines 15–25) builds a `FormData` and `POST`s it to `${API_BASE_URL}/images/upload`.
- The backend handler `upload_image` ([`fastApi-app/api/routes.py`](../fastApi-app/api/routes.py) lines 24–71) generates `uuid.uuid4()`, picks an extension from the original filename (defaulting to `.png`), writes the bytes to `{storage_dir}/{image_id}{suffix}`, and returns `ImageUploadResponse`.

### 3. Click capture (frontend)

- [`UploadFrame.tsx`](../react-front/src/components/widgets/UploadFrame.tsx) lines 30–63 — `handleContainerClick` does two things:
  - Computes a **display** position relative to the container for the click-dot overlay.
  - Computes a **natural** position by scaling the click against `imageRef.current.naturalWidth` / `.naturalHeight`. This is what gets sent to the backend so segmentation always works in real image pixels regardless of how the image is rendered on screen.
- The result lands in `MainPage` via `handleImageClick` ([`MainPage.tsx`](../react-front/src/components/layout/MainPage.tsx) lines 53–56), which stores both positions.

### 4. Run (frontend → backend)

- `MainPage.handleRun` ([`MainPage.tsx`](../react-front/src/components/layout/MainPage.tsx) lines 79–111) builds a `ClickRequest` with `naturalClickPos.x/y` and calls `clickImage(payload)`.
- `clickImage` ([`api/images.ts`](../react-front/src/api/images.ts) lines 27–37) does a JSON `POST` to `/images/click`.
- `handle_click` ([`fastApi-app/api/routes.py`](../fastApi-app/api/routes.py) lines 74–133) hands off to `process_click_on_image` and translates exceptions (`ValueError` → 422, `FileNotFoundError`/`Exception` → 500).

### 5. Backend processing

[`fastApi-app/core/image_processing.py`](../fastApi-app/core/image_processing.py):

1. `process_click_on_image` (lines 126–180) loads the bytes, opens with PIL to validate format and bounds, and writes a debug overlay PNG to `{storage_dir}/point/{image_id}_debug.png` via `_create_debug_click_image` (lines 33–51).
2. It then calls `segment_at_click` (lines 74–123) which lazy-imports `ObjectRemover` (lines 19–30) and invokes `remover.remove_object(image_path=..., x=..., y=..., image_bytes=...)`.
3. The two returned numpy arrays are PNG-encoded with `cv2.imencode`, and `(background_bytes, cutout_bytes, "png")` is returned to the router.

### 6. AI pipeline

[`TestModules/src/core/object_remover.py`](../TestModules/src/core/object_remover.py) — `ObjectRemover.remove_object` (lines 102–197) executes:

1. **Decode** image from `image_bytes` if provided (lines 113–118), else `cv2.imread(image_path)` (lines 119–123).
2. **Depth** — `DepthMappingFacade.map_depth(image)` (line 126), backed by `NearFarBlendedDepthMappingStrategy` (V2 + LiheYoung alpha-blend).
3. **Adapt** — `SamImageAdapter.get_adapted_image(...)` (lines 130–134) caches per `(image_path, x, y)`.
4. **Route** — `BoundaryVarianceRoutingStrategy.choose_input(...)` (lines 138–144) returns a context dict with `input_image`, `expand_pixels`, `use_broad_mask`, `sd_strength`.
5. **Tight SAM mask** — `ImageSegmentationFacade.get_mask_at_point(...)` (lines 150–158) returns `(tight_mask, original_mask)`. `tight_mask` is the SAM-side dilated output (used for inpainting); `original_mask` is the raw SAM prediction (used for the cutout).
6. **Uniform expand** — `MaskRefiner.expand_mask_uniform(radius=3)` (lines 167–170) applied to `tight_mask`.
7. **Hybrid inpaint** — `ImageInpaintingFacade.inpaint(image, mask, strength=...)` (lines 181–185), backed by `HybridInpaintingStrategy` (LaMa + optional SD).
8. **Compose cutout** — `BgraCutoutComposer.compose_original_overlap_bgra(image, original_mask)` (lines 193–196) — uses the raw SAM mask for a tighter cutout boundary.

See [ai-pipeline/core/README.md](ai-pipeline/core/README.md) for the pipeline execution walk.

### 7. Response (backend → frontend)

- `handle_click` ([`fastApi-app/api/routes.py`](../fastApi-app/api/routes.py) lines 86–94) base64-encodes both byte buffers and returns a `ClickResultResponse`.
- `MainPage.handleRun` ([`MainPage.tsx`](../react-front/src/components/layout/MainPage.tsx) lines 99–103) builds `data:image/${result.format};base64,${...}` URLs for both images and stores them in state.
- Two `ResultFrame` instances render them via `<img src={...}>`.

## Failure modes worth knowing

- **`avroom_object_removal` not installed** → `_get_object_remover_class` raises `RuntimeError` ([`image_processing.py`](../fastApi-app/core/image_processing.py) lines 22–27) with a hint to run `pip install -e ./TestModules`.
- **Click out of bounds** → `process_click_on_image` raises `ValueError` ([`image_processing.py`](../fastApi-app/core/image_processing.py) lines 130–139), translated to HTTP 422.
- **Stored file not a valid image** → `UnidentifiedImageError` becomes `ValueError` → 422.
- **Missing SAM checkpoint** → `SamSegmentationStrategy` will try to download from `dl.fbaipublicfiles.com` unless `SAM_AUTO_DOWNLOAD=0` ([`sam_segmentation_strategy.py`](../TestModules/src/ai_engines/segmentation/strategies/sam_segmentation_strategy.py) lines 29–62).
