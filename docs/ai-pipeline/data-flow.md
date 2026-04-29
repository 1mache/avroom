# AI Pipeline Data Flow

A line-by-line trace of `ObjectRemover.remove_object` (in [`TestModules/src/core/objectRemover.py`](../../TestModules/src/core/objectRemover.py)) plus the side calls into engines, routers, and utilities.

## Sequence diagram

```mermaid
sequenceDiagram
    participant Caller
    participant OR as ObjectRemover
    participant Depth as OptimizedDepthFacade
    participant Mapper as ImageDepthMapper
    participant Adapter as SamImageAdapter
    participant Router as BoundaryVarianceRoutingStrategy
    participant SAM as SamFacadeSingleton
    participant Refiner as MaskRefiner
    participant Hybrid as HybridInpainter
    participant LaMa as LamaInpainter
    participant SD as StableDiffusionInpainter
    participant Compose as MaskOverlapRGBAComposer

    Caller->>OR: remove_object(image_path, x, y, image_bytes)
    OR->>OR: cv2.imdecode / cv2.imread (BGR)
    OR->>Depth: get_optimized_depth_map(image)
    Depth->>Mapper: model = "Depth-Anything-V2-Small-hf"
    Depth->>Mapper: get_depth_map(image)
    Depth->>Mapper: model = "depth-anything-small-hf"
    Depth->>Mapper: get_depth_map(image)
    Depth-->>OR: blended uint8 depth
    OR->>Adapter: get_adapted_image(depth, image_path, (x,y))
    Adapter-->>OR: 3-channel RGB depth
    OR->>Router: choose_input(rgb, raw_depth, adapted_depth, x, y)
    Router->>SAM: get_mask_at_point(adapted_depth, x, y, expand_pixels=0)
    SAM-->>Router: probe mask
    Router-->>OR: {input_image, expand_pixels, sd_strength, use_broad_mask}
    OR->>SAM: get_mask_at_point(input_image, x, y, expand_pixels, use_broad_mask)
    SAM->>Refiner: dilate_mask (when expand_pixels > 0)
    SAM-->>OR: tight_mask
    OR->>Refiner: expand_mask_uniform(tight_mask, radius=3)
    Refiner-->>OR: refined mask
    OR->>Hybrid: inpaint(image, mask, strength=sd_strength)
    Hybrid->>LaMa: inpaint(image, mask)
    LaMa-->>Hybrid: lama_result (BGR)
    alt strength > 0.2
        Hybrid->>SD: inpaint(lama_result, mask, strength)
        SD-->>Hybrid: sd_result (BGR)
    else
        Note over Hybrid: skip SD; reuse lama_result
    end
    Hybrid->>Hybrid: unsharp + boundary->interior color nudge
    Hybrid-->>OR: result_image (BGR)
    OR->>Compose: compose_original_overlap_bgra(image, mask)
    Compose-->>OR: original_bgra
    OR-->>Caller: (result_image, original_bgra)
```

## Per-line citations

| Stage | Code | Range |
|---|---|---|
| Decode bytes | [`objectRemover.py`](../../TestModules/src/core/objectRemover.py) | 73–84 |
| Depth call (V2 + LiheYoung blend) | [`OptimizedDepthFacade.py`](../../TestModules/src/ai_engines/depth/OptimizedDepthFacade.py) | 15–38 |
| HF pipeline build/swap | [`ImageDepthMapper.py`](../../TestModules/src/ai_engines/depth/ImageDepthMapper.py) | 37–70 |
| Adapter + cache | [`SamImageAdapter.py`](../../TestModules/src/ai_engines/segmentation/SamImageAdapter.py) | 38–67 |
| Router probe SAM call | [`boundary_variance_strategy.py`](../../TestModules/src/routing/boundary_variance_strategy.py) | 27 |
| Boundary ring + variance | [`boundary_variance_strategy.py`](../../TestModules/src/routing/boundary_variance_strategy.py) | 31–53 |
| Decision + context dict | [`boundary_variance_strategy.py`](../../TestModules/src/routing/boundary_variance_strategy.py) | 57–81 |
| Real SAM call | [`SamFacadeSingleton.py`](../../TestModules/src/ai_engines/segmentation/SamFacadeSingleton.py) | 93–121 |
| Mask resize / binarize | [`objectRemover.py`](../../TestModules/src/core/objectRemover.py) | 13–28, 122 |
| Uniform expand | [`MaskRefiner.py`](../../TestModules/src/utils/MaskRefiner.py) | 57–81 |
| LaMa boundary fill + inpaint | [`LamaInpainter.py`](../../TestModules/src/ai_engines/inpainting/LamaInpainter.py) | 24–81 |
| SD pipeline | [`StableDiffusionInpainter.py`](../../TestModules/src/ai_engines/inpainting/StableDiffusionInpainter.py) | 39–79 |
| Hybrid skip / sharpen / nudge | [`HybridInpainter.py`](../../TestModules/src/ai_engines/inpainting/HybridInpainter.py) | 27–97 |
| Compose BGRA cutout | [`MaskOverlapRGBAComposer.py`](../../TestModules/src/utils/MaskOverlapRGBAComposer.py) | 14–41 |

## Performance notes (rough)

On CPU, with no warm caches:

- Depth: dominates after SD, because two HF models run sequentially.
- SAM: fast (ViT-B is the smallest variant).
- LaMa: very fast.
- SD: slowest at 30 inference steps × 512² with `guidance_scale=10`; only runs when `sd_strength > 0.2`.

On CUDA the order shifts — SD becomes acceptable, depth becomes the slow part again. There is no batching today; each click runs the whole pipeline serially.

## Where shapes can drift

Several places in the pipeline include defensive `_ensure_mask_hw` / `cv2.resize` calls because masks coming back from SAM and depth maps don't always match the original image's `(H, W)` exactly. If you change any tensor sizes upstream, expect to update:

- `_ensure_mask_hw` in [`objectRemover.py`](../../TestModules/src/core/objectRemover.py) lines 13–28.
- The shape guards inside `HybridInpainter.inpaint` ([`HybridInpainter.py`](../../TestModules/src/ai_engines/inpainting/HybridInpainter.py) lines 28–35, 60–67).
- `MaskOverlapRGBAComposer.compose_original_overlap_bgra` lines 21–23.
