# HybridInpainter

**File:** `TestModules/src/ai_engines/inpainting/HybridInpainter.py`

## Responsibility

`HybridInpainter` chains `LamaInpainter` and `StableDiffusionInpainter` into a two-phase composite pipeline. LaMa handles structural removal; SD handles texture refinement and photorealism. It also applies post-processing sharpening and color correction.

It implements `IInpainter` and is the inpainter wired into `ObjectRemover`.

## Two-Phase Strategy

### Phase 1 — Structural Removal (LaMa)

LaMa always runs first. It produces a clean, structure-preserving fill of the masked region with no hallucinated objects. The output is saved to `debug_lama_output.png`.

### Phase 2 — Texture Refinement (SD, conditional)

SD runs only when `strength > 0.2`. The LaMa result is passed as the base image:

```python
if dynamic_strength <= 0.2:
    final_result = lama_result.copy()  # LaMa-only path
else:
    final_result = self.sd.inpaint(lama_result, mask, strength=dynamic_strength)
```

Using LaMa first prevents SD from hallucinating new objects because LaMa has already removed the object and filled in plausible background. SD then only needs to refine the texture of that background, not reconstruct it from scratch.

## Post-Processing Steps

### 1. Size Alignment

Before post-processing, both the result and mask are verified to have the same dimensions as the original image. SD resizes internally to 512×512 and scales back; rounding can cause 1px differences that would cause boolean indexing errors.

### 2. Unsharp Sharpening

```python
sigma = 0.8
blurred = cv2.GaussianBlur(final_result, (0, 0), sigma)
final_result = np.clip(f + 0.6 * (f - blurred), 0, 255).astype(np.uint8)
```

Applied to the full result. A factor of `0.6` at sigma `0.8` sharpens the inpainted area to match the perceived sharpness of the surrounding image.

### 3. Interior Color Nudge

The inpainted area's interior pixels (eroded by 7px kernel, excluding the edge band) are nudged toward the color of the mask boundary:

```python
shift = (boundary_mean - inside_mean) * 0.35
out[interior_only] = np.clip(out[interior_only] + shift, 0, 255)
```

This corrects tonal discrepancies where SD generates a background that is slightly too bright or too dark compared to the surroundings. Edge pixels are intentionally excluded because they may contain reimagined object geometry; shifting them would warp object contours.

## Mask Handling

At entry to `inpaint()`:
- 3-channel masks are collapsed to the first channel
- Mismatched mask/image sizes are corrected via `cv2.INTER_NEAREST` resize

## `strength` Parameter

Received via `**kwargs` from `ObjectRemover`. The currently active router (`BoundaryVarianceRoutingStrategy`) always sets `strength = 0.35`, which triggers the SD pass. SD then makes modest, low-hallucination changes on top of LaMa's clean base.

## Debug Output

| File | Content |
|---|---|
| `debug_lama_output.png` | LaMa result (before SD) |
| `debug_sd_output.png` | Final result after all post-processing |
