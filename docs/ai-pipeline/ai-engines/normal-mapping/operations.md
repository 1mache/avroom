# Normal mapping operations

## Model identifiers

Default: `metric3d_vit_small` via `torch.hub.load("yvanyin/metric3d", ...)`. Debug endpoint query param `hub_model` can select other ViT hub entrypoints.

## Caching

Hub models cached per `(hub_model, device)` via module-level `lru_cache(maxsize=4)` in `Metric3DNormalMappingStrategy`.

## Dependencies

- PyTorch + torchvision (already in root `requirements.txt`)
- `mmengine` (Metric3D hubconf `Config`)
- `timm` (ViT backbone layers used by Metric3D)
- First run downloads the Metric3D repo + checkpoint through torch.hub
- Full OpenMMLab `mmcv` is **not** required: the strategy injects a tiny
  `mmcv.utils` stub when real mmcv is missing (Windows + recent CPU torch
  cannot install mmcv cleanly). Only needed for Metric3D's import-time
  `collect_env` reference.

## Performance

ViT-Small is the debug default. Larger hubs are slower/heavier; the DebugScreen Generate button is explicit (not part of “Run all”) so a normal map does not block every debug batch.

## Failure boundaries

- Non-ViT hub models → `RuntimeError` (no `prediction_normal`)
- Missing CUDA → runs on CPU; decoder `get_bins` is patched off hardcoded
  `device="cuda"` so CPU torch works
- Hub / weight download failures surface on first `map_normals` call
