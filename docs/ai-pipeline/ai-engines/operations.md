# AI Engines operations

## Lazy loading

Heavy stacks (HF depth pipelines, SAM predictor, LaMa, SD pipe) are created behind module-level **`functools.lru_cache`** factories keyed by model identity where needed. Plain facade/strategy instances do **not** cache GPU tensors themselves. The Hunyuan3D-2.1 `gradio_client.Client` is instead created lazily on first `generate()` call and cached on the strategy instance (see [reconstruction-3d/operations.md](../reconstruction-3d/operations.md)).

## Boundaries

- Swapping models or checkpoints is intended to stay inside `strategies/` and env-driven paths (see each domain `operations.md`).
- Core (`ObjectRemover`) should not import concrete strategy modules directly except through defaults in constructor defaults — dependency injection preserves testability.

## Debugging

Most debug PNGs land under `TestModules/outputs/`; filenames differ per domain — see depth/segmentation/inpainting `operations.md` pages.
