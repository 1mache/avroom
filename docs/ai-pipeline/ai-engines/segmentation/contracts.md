# Segmentation contracts

## `get_mask_at_point` / `predict_mask`

- **Inputs:** Adapted depth tensor (H×W×3), integer `(x, y)`, integer `expand_pixels`, boolean `use_broad_mask`.
- **Output:** `(expanded_mask, original_mask)` — single best-candidate pair of 2-D arrays. `original_mask` is the raw SAM prediction (index 1); `expanded_mask` is that mask after any `expand_pixels` dilation (a distinct copy when `expand_pixels == 0`).

## `get_all_masks_for_position` / `predict_all_masks`

- **Inputs:** Same as `get_mask_at_point`.
- **Output:** `tuple[tuple[np.ndarray, np.ndarray], ...]` — one `(expanded_mask, original_mask)` pair per SAM candidate (typically 3: indices 0, 1, 2). Each pair follows the same semantics as the single-candidate output above. SAM is invoked once; dilation is applied independently per candidate.

---

SAM expects geometry-stable input — **RGB scene texture is intentionally not the primary SAM input** in production routing (`adapted_depth`).
