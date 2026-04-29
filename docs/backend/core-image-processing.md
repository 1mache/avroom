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
| `load_image_bytes` | `(image_id, base_dir) -> bytes` | `process_click_on_image` |
| `segment_at_click` | `(image_bytes, x, y, options=None) -> (bg_bytes, cutout_bytes, "png")` | `process_click_on_image` (also a pure entry point if you have bytes already) |
| `process_click_on_image` | `(image_id, base_dir, x, y, options=None) -> (bg_bytes, cutout_bytes, "png")` | `api/routes.handle_click` |

`_get_object_remover_class` and `_create_debug_click_image` are private helpers.

## Lazy import of the AI pipeline

```19:29:fastApi-app/core/image_processing.py
def _get_object_remover_class():
    try:
        from avroom_object_removal.core.objectRemover import ObjectRemover
    except ModuleNotFoundError as exc:
        if exc.name == "avroom_object_removal":
            raise RuntimeError(
                "Missing local package `avroom_object_removal`. Install repo dependencies or run `pip install -e ./TestModules`."
            ) from exc
        raise

    return ObjectRemover
```

Why lazy? It keeps `import core.image_processing` cheap (the model loading happens later, when `ObjectRemover()` is constructed inside `segment_at_click`).

## File resolution

```53:59:fastApi-app/core/image_processing.py
def get_image_path(image_id: str, base_dir: Path) -> Path:
    """Resolve filesystem path for a stored image regardless of extension."""

    candidates = sorted(base_dir.glob(f"{image_id}.*"))
    if not candidates:
        raise FileNotFoundError(f"No stored image found for image_id='{image_id}' in {base_dir}")
    return candidates[0]
```

This is why upload doesn't need to remember the extension — the click can find the file by `image_id.*`.

## Debug PNG

Every click writes a copy of the input with a red dot drawn at the click coordinates to `{base_dir}/tmp/{image_id}_debug.png`:

```32:50:fastApi-app/core/image_processing.py
def _create_debug_click_image(source_image: Image.Image, x: int, y: int, base_dir: Path, image_id: str):
    """Create RGB debug image with a marker drawn at click coordinates."""

    RADIUS = 6
    DEBUG_DIR_SUBPATH = "tmp"

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

## The pipeline call

```86:107:fastApi-app/core/image_processing.py
    if not image_bytes:
        return b"", b"", "png"

    remover = _get_object_remover_class()()
    image_key = f"memory://{hashlib.sha256(image_bytes).hexdigest()}"
    background_bgr, cutout_bgra = remover.remove_object(
        image_path=image_key,
        x=x,
        y=y,
        image_bytes=image_bytes,
    )

    ok_bg, bg_buf = cv2.imencode(".png", background_bgr)
    ok_co, co_buf = cv2.imencode(".png", cutout_bgra)
    if not ok_bg or bg_buf is None:
        raise RuntimeError("Failed to encode background image to PNG.")
    if not ok_co or co_buf is None:
        raise RuntimeError("Failed to encode cutout image to PNG.")

    background_bytes = bg_buf.tobytes()
    cutout_bytes = co_buf.tobytes()
    return background_bytes, cutout_bytes, "png"
```

Things to notice:

- The `image_path` argument is a synthetic `memory://<sha256>` URI used only as a cache key inside `SamImageAdapter`. The real bytes are passed via `image_bytes=`.
- `ObjectRemover()` is constructed **per call**. Most heavy components inside it (SAM, LaMa, depth) are singletons, so subsequent calls only pay the construction cost for thin wrappers.
- The output is always PNG today; the `format` field is hardcoded `"png"`.

## Notes / quirks worth knowing

- `ImageProcessingOptions` is accepted by both `segment_at_click` and `process_click_on_image` but **not** forwarded to `remove_object` — it has no effect today (see lines 89–96). Treat the field as reserved for future use.
- `process_click_on_image` opens the image with PIL only to bounds-check and write the debug overlay. The bytes themselves are passed un-decoded to the pipeline, which uses OpenCV to decode them again ([`objectRemover.py`](../../TestModules/src/core/objectRemover.py) lines 73–79).
- `UnidentifiedImageError` from PIL is converted to `ValueError` so the API returns 422 instead of 500.
