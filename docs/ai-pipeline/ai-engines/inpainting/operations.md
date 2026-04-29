# Inpainting operations

## Hybrid thresholds (strategy constants)

- **`SD_SKIP_THRESHOLD`** — Below this strength, hybrid keeps LaMa-only output (no SD).
- **`SHARPEN_SIGMA`**, **`SHARPEN_AMOUNT`** — Post-pass sharpening parameters.
- Router commonly passes **`sd_strength = 0.35`** during removal pipeline.

## Stable Diffusion defaults (strategy source)

Model id `runwayml/stable-diffusion-inpainting`; typical pipeline settings include fixed inference steps (~30), guidance scale (~10), 512×512 internal canvas — verify exact ints in [`stable_diffusion_inpainting_strategy.py`](../../../../TestModules/src/ai_engines/inpainting/strategies/stable_diffusion_inpainting_strategy.py).

## Caching

LaMa and SD pipelines lazily constructed via module-level caches shared across calls.

## Debug artifacts

Hybrid saves `debug_lama_output`, `debug_sd_output` under `TestModules/outputs/` when enabled by strategy paths.

## Failure boundaries

512² resize inside SD path can amplify blur when skipped thresholds misconfigured — documented rationale lives near hybrid skip logic in source.
