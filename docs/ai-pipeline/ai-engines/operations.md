# AI Engines operations

## Lazy loading

Heavy stacks (HF depth pipelines, SAM predictor, LaMa, SD pipe, Trellis client) are created behind module-level **`functools.lru_cache`** factories keyed by model identity where needed. Plain facade/strategy instances do **not** cache GPU tensors themselves.

## Boundaries

- Swapping models or checkpoints is intended to stay inside `strategies/` and env-driven paths (see each domain `operations.md`).
- Core (`ObjectRemover`) should not import concrete strategy modules directly except through defaults in constructor defaults — dependency injection preserves testability.

## Debugging

Most debug PNGs land under `TestModules/outputs/`; filenames differ per domain — see depth/segmentation/inpainting `operations.md` pages.
