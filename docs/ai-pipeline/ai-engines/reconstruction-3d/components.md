# Reconstruction 3D components

Source: [`TestModules/src/ai_engines/reconstruction_3d/`](../../../../TestModules/src/ai_engines/reconstruction_3d/).

- **`Reconstruction3DFacade`** — Wraps exactly one `Reconstruction3DStrategy`; forwards `generate(...)`. Defaults to `TriposrReconstructionStrategy`; pass another strategy at construction to swap.
- **`Reconstruction3DStrategy`** — ABC for image→GLB backends.
- **`ReconstructionQuality`** + **`PRESETS`** — Named profiles (`FAST`, `BALANCED`, `HIGH`). Trellis uses the full `GenerationParams` table; OpenLRM maps quality mainly to mesh resolution (see [operations.md](operations.md)).
- **`to_pil_rgba`** — Normalizes heterogeneous inputs (bytes, ndarray, PIL, paths).
- **`write_output`** — Dispatches GLB return shape (`bytes`, `Path`, `BinaryIO`).
- **`TriposrReconstructionStrategy`** — Default backend: local PyTorch + vendored TripoSR inference; weights `stabilityai/TripoSR` via HF Hub. Raises **`Triposr3DGenerationError`** on inference/export failures.
- **`OpenLrmReconstructionStrategy`** — Optional backend: local PyTorch + vendored OpenLRM inference; lazy-loaded inferrer. Raises **`OpenLrmReconstructionError`** on inference/export failures.
- **`TrellisReconstructionStrategy`** — Optional backend: Hugging Face Space `microsoft/TRELLIS.2` via `gradio_client`. Raises **`Trellis3DGenerationError`** on Space failures.
- **`_backends/triposr/`** — Vendored TripoSR `tsr/` package (see `LICENSE.TripoSR` under that folder).
- **`_backends/openlrm_v10/`** — Vendored OpenLRM v1.0 `lrm/` package (Apache-2.0 code; weights downloaded at runtime — not stored in-repo). Operational detail: [operations.md](operations.md).
