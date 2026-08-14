# Segmentation components

Source: [`TestModules/src/ai_engines/segmentation/`](../../../../TestModules/src/ai_engines/segmentation/).

- **`ImageSegmentationFacade`** — Public entry point. `get_mask_at_point(...)` for single-best-candidate use (core, router). `get_all_masks_for_position(...)` for all-candidate use (`ObjectSegmentor`). `get_all_masks_for_image(...)` for prompt-free "segment everything" use (`/debug/sam-everything` only).
- **`ImageSegmentationStrategy`** — ABC with two abstract methods (`predict_mask`, `predict_all_masks`) plus one non-abstract method, `predict_everything` (default raises `NotImplementedError` — prompt-free segmentation is SAM-specific, not a general strategy capability).
- **`SamSegmentationStrategy`** — SAM ViT-B, multimask output. `predict_mask` selects index `1`; `predict_all_masks` returns all three candidates; `predict_everything` runs `SamAutomaticMaskGenerator` for prompt-free segmentation (see [contracts.md](contracts.md#get_all_masks_for_image--predict_everything)). Shared SAM prediction extracted into private `_run_sam_predict` helper.
- **`SamImageAdapter`** — Converts single-channel depth to 3-channel input SAM expects; caches last `(image_path, point)` adaptation.
