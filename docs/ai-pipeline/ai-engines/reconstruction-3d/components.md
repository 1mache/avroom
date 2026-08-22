# Reconstruction 3D components

Source: [`TestModules/src/ai_engines/reconstruction_3d/`](../../../../TestModules/src/ai_engines/reconstruction_3d/).

- **`Reconstruction3DFacade`** — Holds one primary `Reconstruction3DStrategy` (default `Hunyuan3D2ReconstructionStrategy`) plus one fixed fallback (`TriposrReconstructionStrategy`, always TripoSR regardless of the injected primary). `generate(...)` calls the primary, retries the fallback on any exception, and raises a `RuntimeError` naming both failures if the fallback also raises.
- **`Reconstruction3DStrategy`** — ABC for image→GLB backends.
- **`ReconstructionQuality`** + **`PRESETS`** — Named profiles (`FAST`, `BALANCED`, `HIGH`). Trellis uses the full `GenerationParams` table; Hunyuan3D-2.1 and TripoSR each map quality via their own local tables instead; OpenLRM maps quality mainly to mesh resolution (see [operations.md](operations.md)).
- **`to_pil_rgba`** — Normalizes heterogeneous inputs (bytes, ndarray, PIL, paths).
- **`write_output`** — Dispatches GLB return shape (`bytes`, `Path`, `BinaryIO`).
- **`Hunyuan3D2ReconstructionStrategy`** — **Default primary backend:** Hugging Face Space `es3d-fi/hunyuan3d-2-1` (a mirror of `tencent/Hunyuan3D-2.1`) via `gradio_client`. Cleans the cutout (alpha threshold + tight center-pad crop) before upload, tries `/generation_all` then falls back to `/shape_generation`. Raises **`Hunyuan3D2GenerationError`** on Space failures.
- **`TriposrReconstructionStrategy`** — **Default fallback backend** (also usable standalone): local PyTorch + vendored TripoSR inference; weights `stabilityai/TripoSR` via HF Hub. Raises **`Triposr3DGenerationError`** on inference/export failures.
- **`OpenLrmReconstructionStrategy`** — Optional backend (explicit injection only): local PyTorch + vendored OpenLRM inference; lazy-loaded inferrer. Raises **`OpenLrmReconstructionError`** on inference/export failures.
- **`TrellisReconstructionStrategy`** — Optional backend (explicit injection only, never constructed by the facade default or fallback): Hugging Face Space `microsoft/TRELLIS.2` via `gradio_client`. Raises **`Trellis3DGenerationError`** on Space failures.
- **`Vfusion3dReconstructionStrategy`** — Optional backend (explicit injection only).
- **`_backends/triposr/`** — Vendored TripoSR `tsr/` package (see `LICENSE.TripoSR` under that folder).
- **`_backends/openlrm_v10/`** — Vendored OpenLRM v1.0 `lrm/` package (Apache-2.0 code; weights downloaded at runtime — not stored in-repo). Operational detail: [operations.md](operations.md).
