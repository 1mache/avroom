# Reconstruction 3D operations

## Default backend (Hunyuan3D-2.1) + automatic fallback (TripoSR)

`Reconstruction3DFacade()` with no arguments constructs `Hunyuan3D2ReconstructionStrategy()` as primary and `TriposrReconstructionStrategy()` as fallback. `generate()` calls the primary; if it raises, the facade retries once against the fallback with identical arguments before giving up.

To use a different backend, inject it explicitly (this replaces only the primary — the fallback is always TripoSR):

```python
from avroom_object_removal.ai_engines.reconstruction_3d import (
    Reconstruction3DFacade,
    OpenLrmReconstructionStrategy,
    TrellisReconstructionStrategy,
)

recon_openlrm = Reconstruction3DFacade(OpenLrmReconstructionStrategy())
recon_trellis = Reconstruction3DFacade(TrellisReconstructionStrategy())
```

## Hunyuan3D-2.1 backend

- **Space id:** `Hunyuan3D2ReconstructionStrategy.DEFAULT_SPACE_ID` = `"es3d-fi/hunyuan3d-2-1"` (a public mirror of `tencent/Hunyuan3D-2.1`).
- **Client:** `gradio_client.Client`, created lazily on first `generate()` call and cached on the strategy instance (`self.__client`) for the strategy's lifetime — not process-wide like the `functools.lru_cache` factories used elsewhere in the pipeline.
- **Auth:** optional `token` constructor arg, else read from `HF_TOKEN` or `HUGGINGFACE_HUB_TOKEN` env vars.
- **Endpoints:** tries `/generation_all` (textured GLB) first; on failure or an empty result, falls back to `/shape_generation` (untextured GLB). Both endpoints are called with the same `steps`/`octree_resolution`/`guidance_scale`/`seed`/`num_chunks` kwargs.
- **Quality mapping:** its own local `_QUALITY_PARAMS: dict[ReconstructionQuality, tuple[int, int]]` maps `FAST`/`BALANCED`/`HIGH` to `(steps, octree_resolution)` — **independent of** the shared `GenerationParams`/`PRESETS` table below (that table is Trellis-specific).
- **Errors:** raises `Hunyuan3D2GenerationError` when both endpoint calls fail.
- **Cutout pre-processing:** before upload, near-transparent alpha pixels (below `_ALPHA_THRESHOLD=10`) are zeroed, then the image is cropped to its visible bounding box and re-centered on a padded transparent square canvas (`_TIGHT_CROP_PADDING_RATIO=1.2`). Both steps are toggleable module-level flags (`_ENABLE_ALPHA_THRESHOLD`, `_ENABLE_TIGHT_CROP`) — they exist to stop the model from rendering a warped floor/blob beneath the object.

## Vendored TripoSR code (isolation)

TripoSR inference code is vendored under:

- `TestModules/src/ai_engines/reconstruction_3d/_backends/triposr/`

The strategy lazy-loads weights via Hugging Face Hub on first use (standard HF cache behavior).

## Vendored OpenLRM code (isolation)

OpenLRM v1.0.0 inference code is vendored under:

- `TestModules/src/ai_engines/reconstruction_3d/_backends/openlrm_v10/`

This keeps all OpenLRM implementation details private to the `reconstruction_3d` domain (under `_backends/`, not `strategies/`) and avoids adding a git submodule.

## Dependencies (pip)

- `gradio_client>=1.4` — Hunyuan3D-2.1 (primary) and Trellis (optional) Space clients.
- `huggingface_hub` (weight download)
- `PyMCubes` (marching cubes mesh extraction, OpenLRM)
- `trimesh` (mesh loading + GLB export, OpenLRM)
- `imageio[ffmpeg]` (OpenLRM video path; not used by Avroom but imported by vendored code)
- Plus existing stack: `torch`, `transformers`, `Pillow`, `numpy`

## Weight download + caching (no repo pollution)

OpenLRM weights are downloaded on first use via `huggingface_hub.hf_hub_download`.

- **Where they land**: by default, the vendored loader writes under the user cache directory:
  - `~/.cache/avroom_openlrm/<model_name>/` (Windows: `C:\\Users\\<you>\\.cache\\avroom_openlrm\\...`)
- **Override**: set `OPENLRM_WEIGHT_CACHE` to redirect weights (e.g. to a dedicated drive or a `.gitignore`'d folder).
- **Hugging Face cache**: auxiliary model downloads (e.g. DINO weights) may also use the Hugging Face cache under `~/.cache/huggingface` unless `HF_HOME` is set. TripoSR weights (`stabilityai/TripoSR`) also land here.

No weights are written into tracked project paths (no files under `TestModules/` are used as a cache destination).

## Trellis backend (optional, not used by default or as fallback)

- **Space id:** `TrellisReconstructionStrategy.DEFAULT_SPACE_ID` = `"microsoft/TRELLIS.2"`.
- **Quality mapping:** uses the full shared `GenerationParams`/`PRESETS` table (resolution, sampling steps, decimation target, texture size).
- **Errors:** raises `Trellis3DGenerationError` on Space failures.
- Only reachable by injecting `TrellisReconstructionStrategy()` explicitly — the facade never constructs it.

## Quality presets

`ReconstructionQuality` (`FAST`/`BALANCED`/`HIGH`) is shared across strategies, but each strategy maps it differently: Hunyuan3D-2.1 and TripoSR use their own local tables; Trellis uses the shared `GenerationParams`/`PRESETS` dict — inspect each strategy module for the numeric fields.

## Operational realities

- Remote Space queues (Hunyuan3D-2.1, Trellis) introduce variable latency unrelated to local GPU availability — this is why the facade always keeps a local fallback (TripoSR) rather than retrying the same Space.
- Failures from the primary strategy are logged at `WARNING` before the fallback runs; if both fail, the caller sees a single `RuntimeError` naming both original exceptions.

## Authentication

Hunyuan3D-2.1 and Trellis both read an optional HF token (`HF_TOKEN` / `HUGGINGFACE_HUB_TOKEN`) for authenticated Space clients — consult each strategy's constructor parameters.
