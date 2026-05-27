# Segmentation components

Source: [`TestModules/src/ai_engines/segmentation/`](../../../../TestModules/src/ai_engines/segmentation/).

- **`ImageSegmentationFacade`** — Public entry point. `get_mask_at_point(...)` for single-best-candidate use (core, router). `get_all_masks_for_position(...)` for all-candidate use (`ObjectSegmentor`).
- **`ImageSegmentationStrategy`** — ABC with two abstract methods: `predict_mask` (returns best `(expanded_mask, original_mask)` pair) and `predict_all_masks` (returns one pair per model candidate).
- **`SamSegmentationStrategy`** — SAM ViT-B, multimask output. `predict_mask` selects index `1`; `predict_all_masks` returns all three candidates. Shared SAM prediction extracted into private `_run_sam_predict` helper.
- **`SamImageAdapter`** — Converts single-channel depth to 3-channel input SAM expects; caches last `(image_path, point)` adaptation.
