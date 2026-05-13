# Reconstruction 3D operations

## Default backend (TripoSR)

`Reconstruction3DFacade` defaults to `TriposrReconstructionStrategy` (local PyTorch inference) using the Hugging Face model **`stabilityai/TripoSR`**.

To use a different backend, inject it explicitly:

```python
from avroom_object_removal.ai_engines.reconstruction_3d import (
    Reconstruction3DFacade,
    OpenLrmReconstructionStrategy,
    TrellisReconstructionStrategy,
)

recon_openlrm = Reconstruction3DFacade(OpenLrmReconstructionStrategy())
recon = Reconstruction3DFacade(TrellisReconstructionStrategy())
```

## Vendored TripoSR code (isolation)

TripoSR inference code is vendored under:

- `TestModules/src/ai_engines/reconstruction_3d/_backends/triposr/`

The strategy lazy-loads weights via Hugging Face Hub on first use (standard HF cache behavior).

## Vendored OpenLRM code (isolation)

OpenLRM v1.0.0 inference code is vendored under:

- `TestModules/src/ai_engines/reconstruction_3d/_backends/openlrm_v10/`

This keeps all OpenLRM implementation details private to the `reconstruction_3d` domain (under `_backends/`, not `strategies/`) and avoids adding a git submodule.

## Dependencies (pip)

The OpenLRM strategy adds runtime dependencies (declared in both `TestModules/pyproject.toml` and root `requirements.txt`):

- `huggingface_hub` (weight download)
- `PyMCubes` (marching cubes mesh extraction)
- `trimesh` (mesh loading + GLB export)
- `imageio[ffmpeg]` (OpenLRM video path; not used by Avroom but imported by vendored code)
- Plus existing stack: `torch`, `transformers`, `Pillow`, `numpy`

## Weight download + caching (no repo pollution)

OpenLRM weights are downloaded on first use via `huggingface_hub.hf_hub_download`.

- **Where they land**: by default, the vendored loader writes under the user cache directory:
  - `~/.cache/avroom_openlrm/<model_name>/` (Windows: `C:\\Users\\<you>\\.cache\\avroom_openlrm\\...`)
- **Override**: set `OPENLRM_WEIGHT_CACHE` to redirect weights (e.g. to a dedicated drive or a `.gitignore`’d folder).
- **Hugging Face cache**: auxiliary model downloads (e.g. DINO weights) may also use the Hugging Face cache under `~/.cache/huggingface` unless `HF_HOME` is set.

No weights are written into tracked project paths (no files under `TestModules/` are used as a cache destination).

## Trellis backend (optional)

Default HF Space id carried by `TrellisReconstructionStrategy` (see source constant, commonly `microsoft/TRELLIS.2`).

## Quality presets

Each preset adjusts synthetic mesh fidelity vs latency trade-offs — inspect `PRESETS` dict for numeric fields.

## Operational realities

- Remote Space queues introduce variable latency unrelated to local GPU availability.
- Failures raise **`Trellis3DGenerationError`** — callers must handle absence of GLB bytes.

## Authentication

Optional HF token wiring enables authenticated Space clients — consult strategy constructor parameters.
