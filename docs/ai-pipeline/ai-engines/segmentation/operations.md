# Segmentation operations

## Environment

- **`SAM_CHECKPOINT_PATH`** — Preferred local `.pth` location.
- **`SAM_AUTO_DOWNLOAD`** — When falsy, skips automatic checkpoint fetch.
- **`SAM_CHECKPOINT_URL`** — Overrides default download URL.
- Default architecture flag **`vit_b`** in strategy.

## Caching

SAM predictor constructed once per process (`lru_cache(maxsize=1)` pattern in strategy loader).

## Debug files (`TestModules/outputs/`)

Typical artifacts include `mask_0.png` … `mask_2.png`, optional `dilated_mask.png`, `best_mask.png`. Probe + final passes overwrite same names during one click.

## Operational notes

Checkpoint download pulls from Facebook CDN unless disabled — ensure outbound network or vendor checkpoints manually.
