# Segmentation contracts

- **Inputs:** Adapted depth tensor (H×W×3), integer `(x, y)`, integer `expand_pixels`, boolean `use_broad_mask`.
- **Output:** 2D mask array; downstream expects near-binary semantics (0 vs foreground).

SAM expects geometry-stable input — **RGB scene texture is intentionally not the primary SAM input** in production routing (`adapted_depth`).
