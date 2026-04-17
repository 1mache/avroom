# ObjectRemover

**File:** `TestModules/src/core/objectRemover.py`

## Responsibility

`ObjectRemover` is the main orchestrator of the entire object-removal pipeline. It owns and wires all subsystems together and executes them in the correct order. It is the only class the API layer calls.

## Construction

```python
remover = ObjectRemover()
```

On construction, `ObjectRemover` instantiates all pipeline components:

| Attribute | Type | Purpose |
|---|---|---|
| `self.sam` | `SamFacadeSingleton` | Segmentation model |
| `self.inpainter` | `HybridInpainter` (via `IInpainter`) | Inpainting engine |
| `self.depth_facade` | `OptimizedDepthFacade(threshold=100)` | Depth map generation |
| `self.sam_adapter` | `SamImageAdapter` | depth → RGB conversion + cache |
| `self.router` | `BoundaryVarianceRoutingStrategy(sam_facade=self.sam)` | Routing decision |
| `self.mask_refiner` | `MaskRefiner(depth_tolerance=10)` | Post-SAM mask refinement |
| `self.image_saver` | `DebugImageSaver` | Debug output writer |

## Public API

### `remove_object(image_path, x, y, depth_output_flag=False, image_bytes=None)`

**Returns:** `(background_bgr: np.ndarray, cutout_bgra: np.ndarray)`

| Parameter | Type | Description |
|---|---|---|
| `image_path` | `str` | Path to the source image file. Used as the cache key for `SamImageAdapter`. |
| `x`, `y` | `int` | Click coordinates in pixels, origin top-left. |
| `depth_output_flag` | `bool` | Reserved; not currently used in the pipeline. |
| `image_bytes` | `bytes \| None` | If provided, the image is decoded from these bytes directly instead of reading `image_path` from disk. |

### `remove_object_test()`

Convenience wrapper for the OpenCV GUI test harness (`GuiTestClicker`). Calls `remove_object` using previously set `self.image_path` and `self.point`. Returns `None` if either is unset.

### `set_image(image_path)` / `set_point(x, y)`

Setters used by `GuiTestClicker` before calling `remove_object_test()`.

## Execution Steps

### Step 1 — Depth Map

```python
optimized_depth = self.depth_facade.get_optimized_depth_map(image)
```

Runs both depth models (V2 + LiheYoung) and returns a blended uint8 grayscale depth map. See [`optimized-depth-facade.md`](../ai-engines/depth/optimized-depth-facade.md).

### Step 2 — Depth Adaptation

```python
adapted_for_sam = self.sam_adapter.get_adapted_image(
    raw_data=optimized_depth, image_id=image_path, point=(x, y)
)
```

Converts the grayscale depth map to a 3-channel RGB array suitable for SAM. The result is cached by `(image_id, x, y)`. See [`sam-image-adapter.md`](../ai-engines/segmentation/sam-image-adapter.md).

### Step 3 — Routing Decision

```python
run_context = self.router.choose_input(
    rgb_image=image, raw_depth=optimized_depth,
    adapted_depth=adapted_for_sam, x=x, y=y
)
```

The router analyzes the depth geometry around the click and returns a `run_context` dict that controls downstream behavior:

| Key | Type | Meaning |
|---|---|---|
| `input_image` | `np.ndarray` | Image to pass to SAM (adapted depth or RGB) |
| `sd_strength` | `float` | Stable Diffusion strength for the inpainter |
| `use_broad_mask` | `bool` | Whether to request the broader SAM mask |
| `expand_pixels` | `int` | Dilation applied to the SAM mask inside the facade |

See [`routing/overview.md`](../routing/overview.md).

### Step 4 — SAM Segmentation

```python
tight_mask = self.sam.get_mask_at_point(
    run_context['input_image'], x, y,
    expand_pixels=run_context.get('expand_pixels', 14),
    use_broad_mask=run_context['use_broad_mask']
)
tight_mask = _ensure_mask_hw(tight_mask, image.shape[:2])
```

SAM returns a binary mask of the object. The `_ensure_mask_hw` helper resizes the mask to exactly match the original image dimensions using nearest-neighbor interpolation. See [`sam-facade.md`](../ai-engines/segmentation/sam-facade.md).

### Step 5 — Mask Refinement

```python
mask = self.mask_refiner.expand_mask_uniform(original_mask=tight_mask, radius=3)
mask = _ensure_mask_hw(mask, image.shape[:2])
```

Applies a small uniform 3px expansion with a 2px downward bias. This catches edge pixels that SAM misses by 1–3px and ensures the LaMa boundary fill samples from true background. See [`mask-refiner.md`](../utils/mask-refiner.md).

### Step 6 — Inpainting

```python
result_image = self.inpainter.inpaint(image, mask, strength=run_context['sd_strength'])
```

Passes the original image and refined mask to `HybridInpainter`, which runs LaMa first and optionally Stable Diffusion if `strength > 0.2`. See [`hybrid-inpainter.md`](../ai-engines/inpainting/hybrid-inpainter.md).

### Step 7 — Cutout Composition

```python
original_bg_ra = MaskOverlapRGBAComposer.compose_original_overlap_bgra(
    original_bgr=image, mask=mask
)
```

Creates a BGRA image containing the original pixels only within the mask area, with alpha=0 everywhere else. See [`mask-overlap-composer.md`](../utils/mask-overlap-composer.md).

## Helper: `_ensure_mask_hw`

A module-level helper that normalizes a mask to a target `(H, W)`:
- Drops a spurious channel dimension if present
- Resizes using `cv2.INTER_NEAREST` to preserve binary semantics
- Normalizes to `uint8` (0 or 255)

## Debug Output

At each stage, `self.image_saver.save(name, array)` writes a `.png` to `TestModules/outputs/`. See the full list in [`data-flow.md`](../../shared/data-flow.md#debug-artifacts-written-to-disk).
