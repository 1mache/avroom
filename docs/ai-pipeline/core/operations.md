# Core operations

## Configuration knobs

- **Mask refinement:** `MaskRefiner.expand_mask_uniform(..., radius=3)` on the refined binary mask before inpainting.
- **`MaskRefiner(depth_tolerance=10)`** — Only affects `expand_and_clip`; the main pipeline does not call that path.
- **`depth_output_flag`** — No runtime branching.

## Caching and performance

- **`ObjectRemover()`** is constructed per FastAPI click; collaborator objects are cheap.
- Heavy models live behind module-level `functools.lru_cache` inside strategies (SAM, depth pipelines, LaMa, SD), so loads amortize across requests.

## Debug artifacts (orchestrator)

Written via `DebugImageSaver` under `TestModules/outputs/` (names without extension in code; saved as PNG):

- `optimized_depth`, `adapted_for_sam`, `tight_mask`, `debug_tight_mask_overlay`, `mask`, `debug_mask_overlay`, `final_removed_object`

See also engine-level debug files under segmentation and inpainting partials.

## Failure boundaries

- Invalid image bytes or out-of-range clicks surface from the FastAPI bridge before or inside pipeline decode.
- Missing ML weights or CUDA OOM manifest inside domain strategies; HTTP mapping is described in backend docs.
