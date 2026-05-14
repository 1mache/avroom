# Segmentation contracts

- **Inputs:** Adapted depth tensor (H×W×3), integer `(x, y)`, integer `expand_pixels`, boolean `use_broad_mask`.
- **Output:** `(expanded_mask, original_mask)` tuple of 2D arrays; downstream expects near-binary semantics (0 vs foreground). `original_mask` is the raw SAM prediction; `expanded_mask` is that mask after any `expand_pixels` dilation (a distinct copy when `expand_pixels == 0`).

SAM expects geometry-stable input — **RGB scene texture is intentionally not the primary SAM input** in production routing (`adapted_depth`).
