# Segmentation contracts

## `get_mask_at_point` / `predict_mask`

- **Inputs:** Adapted depth tensor (H×W×3), integer `(x, y)`, integer `expand_pixels`, boolean `use_broad_mask`.
- **Output:** `(expanded_mask, original_mask)` — single best-candidate pair of 2-D arrays. `original_mask` is the raw SAM prediction (index 1); `expanded_mask` is that mask after any `expand_pixels` dilation (a distinct copy when `expand_pixels == 0`).

## `get_all_masks_for_position` / `predict_all_masks`

- **Inputs:** Same as `get_mask_at_point`.
- **Output:** `tuple[tuple[np.ndarray, np.ndarray], ...]` — one `(expanded_mask, original_mask)` pair per SAM candidate (typically 3: indices 0, 1, 2). Each pair follows the same semantics as the single-candidate output above. SAM is invoked once; dilation is applied independently per candidate.

## `get_all_masks_for_image` / `predict_everything`

Prompt-free ("segment everything") mode — no `(x, y)` point. Backs the `/debug/sam-everything` FastAPI endpoint only (see [backend/api-endpoints.md](../../../backend/api-endpoints.md#debug-endpoints)); not used by production point-click segmentation.

- **Inputs:** Image array (RGB-shaped contract, same as `predict_mask` — production callers pass the adapted depth map), keyword-only `points_per_side` (probe grid density, default `16`), `pred_iou_thresh` (default `0.88`), `stability_score_thresh` (default `0.95`), `min_mask_region_area` (default `0`).
- **Output:** `tuple[np.ndarray, ...]` — boolean 2-D masks, sorted by area descending.
- Non-abstract on `ImageSegmentationStrategy` (default raises `NotImplementedError`) rather than `@abstractmethod`, since prompt-free segmentation is SAM-specific and forcing it on every future strategy would break them.
- `SamSegmentationStrategy.predict_everything` runs `SamAutomaticMaskGenerator` (a `points_per_side × points_per_side` grid of foreground-point probes — runtime scales with the square of `points_per_side`) via `_load_sam_mask_generator`, a `functools.lru_cache`'d loader keyed on `(checkpoint_path, model_type, device, points_per_side, pred_iou_thresh, stability_score_thresh, min_mask_region_area)` that reuses the already-loaded `SamPredictor`'s model — no duplicate 370MB checkpoint load per configuration.

---

SAM expects geometry-stable input — **RGB scene texture is intentionally not the primary SAM input** in production routing (`adapted_depth`).
