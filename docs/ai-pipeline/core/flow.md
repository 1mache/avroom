# Core execution and data flow

Order matches [`object_remover.py`](../../../TestModules/src/core/object_remover.py) `remove_object`.

## Stage sequence

1. Decode `image_bytes` if present, else load `image_path` as BGR.
2. **Depth** — `DepthMappingFacade.map_depth(image)` produces single-channel depth.
3. **Adapt** — `SamImageAdapter.get_adapted_image(depth, image_path, (x, y))` builds 3-channel SAM input (cached per path + point).
4. **Route** — `SegmentationRoutingStrategy.choose_input(...)` returns a run context (probe SAM runs inside routing).
5. **Segment** — `ImageSegmentationFacade.get_mask_at_point(...)` produces tight mask using routed inputs.
6. **Refine** — `MaskRefiner.expand_mask_uniform(..., radius=3)` expands mask before inpainting.
7. **Inpaint** — `ImageInpaintingFacade.inpaint(image, mask, strength=sd_strength)` fills the hole.
8. **Compose** — `BgraCutoutComposer.compose_original_overlap_bgra(image, mask)` builds cutout from original pixels.

Data threading: BGR image and depth-derived tensors flow forward; masks stay aligned with image dimensions after `_ensure_mask_hw`.
