# Segmentation operations

## Environment

- **`SAM_CHECKPOINT_PATH`** — Preferred local `.pth` location.
- **`SAM_AUTO_DOWNLOAD`** — When falsy, skips automatic checkpoint fetch.
- **`SAM_CHECKPOINT_URL`** — Overrides default download URL.
- Default architecture flag **`vit_b`** in strategy.

## Caching

SAM predictor constructed once per process (`lru_cache(maxsize=1)` pattern in strategy loader).

## Debug files (`TestModules/outputs/`)

**`get_mask_at_point` / `predict_mask` pass:**

- `mask_0.png` … `mask_2.png` — raw SAM candidates.
- `dilated_mask.png` — routing-expanded best candidate (when `expand_pixels > 0`).
- `best_mask.png` — final output of `predict_mask` (index 1, possibly dilated).

**`get_all_masks_for_position` / `predict_all_masks` pass:**

- `mask_0.png` … `mask_2.png` — same raw SAM candidates (shared SAM call).
- `dilated_mask_0.png` … `dilated_mask_2.png` — per-candidate dilated versions (when `expand_pixels > 0`).

Probe + final passes overwrite same names during one click.

## Operational notes

Checkpoint download pulls from Facebook CDN unless disabled — ensure outbound network or vendor checkpoints manually.
