# Depth operations

## Model identifiers

Near/far defaults are constants on `NearFarBlendedDepthMappingStrategy` (see source for exact HF ids).

## Caching

HF depth pipelines cached per `(model_name, task)` via module-level `lru_cache(maxsize=4)` inside depth loader helpers.

## Performance

Both nets run per click when using default blend — dominant CPU/GPU cost alongside inpainting.

## Failure boundaries

HF/transformers failures surface during pipeline inference (missing weights, CUDA issues).
