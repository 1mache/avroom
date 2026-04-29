# Segmentation components

Source: [`TestModules/src/ai_engines/segmentation/`](../../../../TestModules/src/ai_engines/segmentation/).

- **`ImageSegmentationFacade`** — `get_mask_at_point(...)` entry used by core and router.
- **`ImageSegmentationStrategy`** — ABC (`predict_mask`).
- **`SamSegmentationStrategy`** — SAM ViT-B, multimask output, selects mask index `1`.
- **`SamImageAdapter`** — Converts single-channel depth to 3-channel input SAM expects; caches last `(image_path, point)` adaptation.
