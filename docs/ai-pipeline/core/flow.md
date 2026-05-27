# Core execution and data flow

## `ObjectRemover.remove_object` — full pipeline

Order matches [`object_remover.py`](../../../TestModules/src/core/object_remover.py).

1. Decode `image_bytes` if present, else load `image_path` as BGR.
2. **Depth** — `DepthMappingFacade.map_depth(image)` produces single-channel depth.
3. **Adapt** — `SamImageAdapter.get_adapted_image(depth, image_path, (x, y))` builds 3-channel SAM input (cached per path + point).
4. **Route** — `SegmentationRoutingStrategy.choose_input(...)` returns a run context (probe SAM runs inside routing).
5. **Segment** — `ImageSegmentationFacade.get_mask_at_point(...)` returns `(tight_mask, original_mask)`. `tight_mask` is SAM's output after the routing-requested `expand_pixels` dilation; `original_mask` is the raw SAM prediction.
6. **Refine** — `MaskRefiner.expand_mask_uniform(..., radius=3)` expands `tight_mask` before inpainting.
7. **Inpaint** — `ImageInpaintingFacade.inpaint(image, mask, strength=sd_strength)` fills the hole.
8. **Compose** — `BgraCutoutComposer.compose_original_overlap_bgra(image, original_mask)` builds cutout from original pixels using the tighter raw mask.

Returns `(background_bgr, cutout_bgra)`.

## `ObjectSegmentor.get_mask_for_object_at_position` — segmentation only

Stages 1–4 identical to `remove_object`. Stage 5 uses the multi-mask variant:

5. **Segment (all candidates)** — `ImageSegmentationFacade.get_all_masks_for_position(...)` returns one `(expanded_mask, original_mask)` pair per SAM candidate.

Then, for each candidate:

6. **Refine** — `MaskRefiner.expand_mask_uniform(..., radius=3)` applied to `expanded_mask` → `refined_mask`.
7. **Compose** — `BgraCutoutComposer.compose_original_overlap_bgra(image, original_mask)` builds `cutout_bgra` from the raw (tight) mask.

Returns a tuple of `(refined_mask, cutout_bgra)` pairs — one per candidate.

Inpainting (stage 7 of `remove_object`) is intentionally omitted.

## `BackgroundInpainter.cut_mask_from_image` — inpainting only

Accepts an original BGR image and a mask (typically a `refined_mask` from `ObjectSegmentor`):

4. **Inpaint** — `ImageInpaintingFacade.inpaint(original_image, mask)` fills the masked region.

Returns `result_image` (BGR, same spatial size as input).

---

Data threading: BGR image and depth-derived tensors flow forward; masks stay aligned with image dimensions after `ensure_mask_hw` (`_mask_utils.py`).
