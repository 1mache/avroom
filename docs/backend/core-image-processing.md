# core/image_processing.py

[`fastApi-app/core/image_processing.py`](../../fastApi-app/core/image_processing.py) is the only module that talks to the AI pipeline. Everything else in the backend is HTTP plumbing.

## Responsibilities

- Resolve a stored image by `image_id` (any extension).
- Validate the click is inside the image.
- Write a debug overlay PNG showing where the click landed.
- Lazily import `ObjectRemover` from `avroom_object_removal` so the backend can boot even if the package isn't installed (the actual call still fails clearly).
- Run the pipeline and PNG-encode the two returned numpy arrays.

## Public surface

| Function | Signature | Used by |
|---|---|---|
| `get_image_path` | `(image_id, base_dir) -> Path` | `load_image_bytes` |
| `load_image_bytes` | `(image_id, base_dir) -> bytes` | `process_click_on_image` (original upload only) |
| `load_canvas_bytes` | `(image_id, base_dir) -> bytes` | `segment_candidates_on_image`, `inpaint_selected_mask_on_image` |
| `segment_at_click` | `(image_bytes, x, y, options=None) -> (bg_bytes, cutout_bytes, "png")` | `process_click_on_image` |
| `process_click_on_image` | `(image_id, base_dir, x, y, options=None) -> (bg_bytes, cutout_bytes, "png")` | `api/routes.handle_click` (legacy) |
| `segment_candidates_on_image` | `(image_id, base_dir, x, y, options=None) -> list[(mask_id, cutout_bytes)]` | `api/routes.segment_image` |
| `inpaint_selected_mask_on_image` | `(image_id, mask_id, base_dir) -> (bg_bytes, cutout_bytes, "png")` | `api/routes.inpaint_mask` |

`_get_object_remover_class`, `_get_object_segmentor_class`, `_get_background_inpainter_class`, and `_create_debug_click_image` are private helpers.

## Progressive canvas — `load_canvas_bytes`

`load_canvas_bytes` (lines 105–138) is the image loader used by the two-step pipeline (`segment_candidates_on_image` and `inpaint_selected_mask_on_image`). It enables **progressive removal**: if `{uid}_background.png` already exists, it loads that canvas (the accumulated result of all prior removals) rather than the original upload. If no background exists yet (first object), it falls back to `load_image_bytes`.

This means each new segmentation and inpainting operates on the already-cleaned room image, not on the original with prior objects still visible.

```python
canvas_path = current_background_path(base_dir, image_id)   # {uid}_background.png
if canvas_path.exists():
    return canvas_path.read_bytes()          # progressive: use latest inpainted state
return load_image_bytes(image_id, base_dir)  # first object: use original upload
```

`current_background_path` is imported from [`core/object_storage.py`](../../fastApi-app/core/object_storage.py). `process_click_on_image` (legacy) still calls `load_image_bytes` directly and is not part of the progressive canvas path.

## Lazy import of the AI pipeline

```22:33:fastApi-app/core/image_processing.py
def _get_object_remover_class():
    try:
        from avroom_object_removal import ObjectRemover
    except ModuleNotFoundError as exc:
        if exc.name == "avroom_object_removal":
            raise RuntimeError(
                "Missing local package `avroom_object_removal`. Install repo dependencies or run `pip install -e ./TestModules`."
            ) from exc
        raise

    return ObjectRemover
```

`ObjectRemover` is the master Facade re-exported from the top of the package — see [ai-pipeline/core/README.md](../ai-pipeline/core/README.md).

Why lazy? It keeps `import core.image_processing` cheap (the model loading happens later, when `ObjectRemover()` is constructed inside `segment_at_click`).

## File resolution

```85:91:fastApi-app/core/image_processing.py
def get_image_path(image_id: str, base_dir: Path) -> Path:
    """Resolve filesystem path for a stored image regardless of extension."""

    candidates = sorted(base_dir.glob(f"{image_id}.*"))
    if not candidates:
        raise FileNotFoundError(f"No stored image found for image_id='{image_id}' in {base_dir}")
    return candidates[0]
```

This is why upload doesn't need to remember the extension — the click can find the file by `image_id.*`.

## Debug PNG

Every click writes a copy of the input with a red dot drawn at the click coordinates to `{base_dir}/point/{image_id}_debug.png`:

```64:82:fastApi-app/core/image_processing.py
def _create_debug_click_image(source_image: Image.Image, x: int, y: int, base_dir: Path, image_id: str):
    """Create RGB debug image with a marker drawn at click coordinates."""

    RADIUS = 6
    DEBUG_DIR_SUBPATH = "point"

    debug_image: Image.Image = source_image.convert("RGB")
    draw = ImageDraw.Draw(debug_image)
    draw.ellipse(
        (x - RADIUS, y - RADIUS, x + RADIUS, y + RADIUS),
        fill="red",
        outline="white",
        width=2,
    )

    tmp_dir = base_dir / DEBUG_DIR_SUBPATH
    tmp_dir.mkdir(parents=True, exist_ok=True)
    debug_image_path = tmp_dir / f"{image_id}_debug.png"
    debug_image.save(debug_image_path)
```

These accumulate forever; there is no cleanup.

## The pipeline call (legacy `segment_at_click`)

`segment_at_click` (lines 195–244) is used only by the legacy `POST /images/click` one-step endpoint. The modern two-step flow uses `segment_candidates_on_image` + `inpaint_selected_mask_on_image` instead.

```212:227:fastApi-app/core/image_processing.py
    remover = _get_object_remover_class()()
    image_key = f"memory://{hashlib.sha256(image_bytes).hexdigest()}"

    logger.info("Running ObjectRemover: image_key=%s click=(%d,%d)", image_key, x, y)
    background_bgr, cutout_bgra = remover.remove_object(
        image_path=image_key,
        x=x,
        y=y,
        image_bytes=image_bytes,
    )
```

Things to notice:

- The `image_path` argument is a synthetic `memory://<sha256>` URI used only as a cache key inside `SamImageAdapter`. The real bytes are passed via `image_bytes=`.
- `ObjectRemover()` is constructed **per call**. The strategy classes themselves are cheap; the heavy resources (SAM predictor, LaMa, SD pipe, HF depth pipelines) are loaded exactly once per process behind module-level `functools.lru_cache` factories, so subsequent calls only pay thin wrapper construction.
- The output is always PNG today; the `format` field is hardcoded `"png"`.

## Notes / quirks worth knowing

- `ImageProcessingOptions` is accepted by both `segment_at_click` and `process_click_on_image` but **not** forwarded to `remove_object` — it has no effect today (see lines 89–96). Treat the field as reserved for future use.
- `process_click_on_image` opens the image with PIL only to bounds-check and write the debug overlay. The bytes themselves are passed un-decoded to the pipeline, which uses OpenCV to decode them again ([`object_remover.py`](../../TestModules/src/core/object_remover.py) lines 113–123).
- `UnidentifiedImageError` from PIL is converted to `ValueError` so the API returns 422 instead of 500.
