# Reconstruction 3D components

Source: [`TestModules/src/ai_engines/reconstruction_3d/`](../../../../TestModules/src/ai_engines/reconstruction_3d/).

- **`Reconstruction3DFacade`** — Wraps `Reconstruction3DStrategy`; forwards `generate(...)`.
- **`Reconstruction3DStrategy`** — ABC for image→mesh backends.
- **`ReconstructionQuality`** + **`PRESETS`** — Named profiles (`FAST`, `BALANCED`, `HIGH`).
- **`to_pil_rgba`** — Normalizes heterogeneous inputs (bytes, ndarray, PIL, paths).
- **`write_output`** — Dispatches GLB return shape (`bytes`, `Path`, `BinaryIO`).
- **`TrellisReconstructionStrategy`** — Calls HF Space endpoints for Trellis 2 pipeline.
