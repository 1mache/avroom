# Image Processing Bridge

**File:** `fastApi-app/core/image_processing.py`

## Responsibility

This module bridges the FastAPI layer to the `TestModules` CV/ML pipeline. It handles:
- Resolving stored image files by `image_id`
- Drawing a debug overlay for each click
- Patching `sys.path` and `sys.modules` so `TestModules/src` packages resolve correctly
- Calling `ObjectRemover.remove_object()` and encoding results back to bytes

## Functions

### `get_image_path(image_id, base_dir) → Path`

Scans `base_dir` for any file matching `<image_id>.*` and returns the first match. Raises `FileNotFoundError` if no file is found. This handles any extension without requiring the caller to know it.

### `load_image_bytes(image_id, base_dir) → bytes`

Resolves the path via `get_image_path` and returns the raw bytes. Used by `process_click_on_image`.

### `process_click_on_image(image_id, base_dir, x, y, options) → (bytes, bytes, str)`

High-level entry point called by `routes.handle_click()`:

1. Resolves the stored image path
2. Draws a debug overlay (red dot at click position) and saves it to `images/tmp/<image_id>_debug<ext>`
3. Delegates to `segment_at_click()`
4. Returns `(background_bytes, cutout_bytes, format)`

### `segment_at_click(image_bytes, x, y, options) → (bytes, bytes, str)`

Core bridge function. This is where the `sys.path` patching happens.

#### The sys.path / sys.modules Patching Problem

`fastApi-app` has its own `core` package (`fastApi-app/core/`). `TestModules/src` also has a `core` package (`TestModules/src/core/`). Without patching, `from core.objectRemover import ObjectRemover` would try to import from fastApi-app's `core`, not TestModules'.

The fix:

```python
test_src_dir = Path(__file__).resolve().parents[2] / "TestModules" / "src"

# 1. Add TestModules/src to sys.path
if str(test_src_dir) not in sys.path:
    sys.path.insert(0, str(test_src_dir))

# 2. Register stub package modules pointing to TestModules paths
_ensure_stub_pkg("core",       test_src_dir / "core")
_ensure_stub_pkg("utils",      test_src_dir / "utils")
_ensure_stub_pkg("ai_engines", test_src_dir / "ai_engines")
_ensure_stub_pkg("routing",    test_src_dir / "routing")
```

`_ensure_stub_pkg` creates a minimal `types.ModuleType` with `__path__` set to the TestModules directory, overriding whatever was previously in `sys.modules` for that name.

The original module references are saved beforehand and **restored in the `finally` block** so that subsequent requests within the same process see the normal fastApi-app packages.

#### Full Flow Inside `segment_at_click`

1. Save original `sys.modules` entries for `core`, `utils`, `ai_engines`, `routing`
2. Patch `sys.path` and `sys.modules` with TestModules stubs
3. Lazy import `ObjectRemover` from the stubbed `core.objectRemover`
4. Decode `image_bytes` with PIL, convert to RGB, save as a temp PNG file
   - Temp path: `<tempdir>/avroom_object_remover/<uuid>.png`
5. Call `remover.remove_object(str(tmp_image_path), x, y)`
6. Encode `background_bgr` with `cv2.imencode(".png", ...)`
7. Encode `cutout_bgra` with `cv2.imencode(".png", ...)`
8. Delete the temp PNG (best-effort)
9. Restore `sys.modules` in `finally`
10. Return `(background_bytes, cutout_bytes, "png")`

#### Why a Temp PNG?

`ObjectRemover.remove_object()` accepts `image_bytes` as an optional parameter but also requires `image_path` for the `SamImageAdapter` cache key. The temp PNG path satisfies the cache key requirement consistently. Passing bytes directly works too but the path serves as the stable identity string.
