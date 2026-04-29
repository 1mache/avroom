# Pipeline Outputs

Every call to `ObjectRemover.remove_object` writes a constellation of debug PNGs to `TestModules/outputs/`. Plus the final return value is fed back to the FastAPI layer and never persisted. This page enumerates exactly what shows up where.

## Filesystem outputs (per call)

All saved via [`DebugImageSaver`](../../TestModules/src/utils/DebugImageSaver.py) into `TestModules/outputs/`. Filenames are overwritten on every run.

| Filename | Written by | What it shows |
|---|---|---|
| `optimized_depth.png` | [`objectRemover.py`](../../TestModules/src/core/objectRemover.py) line 89 | Alpha-blended depth map (uint8 grayscale). |
| `adapted_for_sam.png` | [`objectRemover.py`](../../TestModules/src/core/objectRemover.py) line 99 | Depth converted to 3-channel RGB (what SAM actually sees). |
| `mask_0.png`, `mask_1.png`, `mask_2.png` | [`SamFacadeSingleton.py`](../../TestModules/src/ai_engines/segmentation/SamFacadeSingleton.py) line 111 | All three SAM candidate masks (the pipeline picks `mask_1`). |
| `dilated_mask.png` | [`SamFacadeSingleton.py`](../../TestModules/src/ai_engines/segmentation/SamFacadeSingleton.py) line 119 | The picked mask after `expand_pixels` dilation, only when `expand_pixels > 0`. |
| `best_mask.png` | [`SamFacadeSingleton.py`](../../TestModules/src/ai_engines/segmentation/SamFacadeSingleton.py) line 120 | The final mask returned by `get_mask_at_point`. |
| `tight_mask.png` | [`objectRemover.py`](../../TestModules/src/core/objectRemover.py) line 123 | The SAM mask after `_ensure_mask_hw` resize. |
| `debug_tight_mask_overlay.png` | [`objectRemover.py`](../../TestModules/src/core/objectRemover.py) line 132 | Original image with the tight mask painted pure white. |
| `mask.png` | [`objectRemover.py`](../../TestModules/src/core/objectRemover.py) line 145 | Mask after `MaskRefiner.expand_mask_uniform(radius=3)`. |
| `debug_mask_overlay.png` | [`objectRemover.py`](../../TestModules/src/core/objectRemover.py) line 156 | Original image with the refined mask painted pure white. |
| `debug_lama_output.png` | [`HybridInpainter.py`](../../TestModules/src/ai_engines/inpainting/HybridInpainter.py) line 40 | Result of LaMa phase before SD. |
| `debug_sd_output.png` | [`HybridInpainter.py`](../../TestModules/src/ai_engines/inpainting/HybridInpainter.py) line 94 | Final result after SD + sharpen + color nudge. |
| `final_removed_object.png` | [`objectRemover.py`](../../TestModules/src/core/objectRemover.py) line 169 | Same as `debug_sd_output` (the inpainted result). |

### Note: the router calls SAM too

`BoundaryVarianceRoutingStrategy.choose_input` calls `sam.get_mask_at_point` first, with `expand_pixels=0`, to compute the boundary ring ([`boundary_variance_strategy.py`](../../TestModules/src/routing/boundary_variance_strategy.py) line 27). Because every `get_mask_at_point` call writes its own `mask_*.png` / `best_mask.png`, the final files in `outputs/` reflect the **second** SAM call (the real one), not the probe.

If you ever want to inspect the probe mask separately, you'll need to either rename the saves inside the router or temporarily disable the second SAM call.

## Function return value

`ObjectRemover.remove_object` returns:

```183:183:TestModules/src/core/objectRemover.py
        return result_image, original_bg_ra
```

| Value | Type | Shape | Purpose |
|---|---|---|---|
| `result_image` | `np.ndarray (uint8)` | `(H, W, 3)` BGR | The "object removed" image. Becomes `background_b64` in the API response. |
| `original_bg_ra` | `np.ndarray (uint8)` | `(H, W, 4)` BGRA | The original image masked to the object area. Alpha=0 outside the mask, RGB also zeroed outside. Becomes `cutout_b64`. |

These are PNG-encoded by `cv2.imencode` in [`fastApi-app/core/image_processing.py`](../../fastApi-app/core/image_processing.py) lines 98–106 and never written to disk.

## Backend-side artifact

The FastAPI layer also writes its own debug image to `{image_storage_dir}/tmp/{image_id}_debug.png` ([`image_processing.py`](../../fastApi-app/core/image_processing.py) lines 32–50) — the input image with a red dot drawn at the click. This is unrelated to the pipeline's `outputs/` directory.

## Cleanup

Nothing is cleaned up automatically. Both `TestModules/outputs/` and `fastApi-app/images/tmp/` accumulate files indefinitely. The `.gitignore` keeps them out of the repo, but disk usage is on you.
