# Reconstruction 3D

**What this is:** **Image-to-GLB** mesh generation from a cutout (or any image `to_pil_rgba` accepts). The facade holds one primary strategy plus one automatic fallback strategy.

**When it runs:** Via `core/inference_pool` (`JobKind.GENERATE_3D`) from two backend routes — `POST /3d/test-3d` ([`fastApi-app/api/model_3d.py`](../../../../fastApi-app/api/model_3d.py)) and `POST /images/novel-view` ([`fastApi-app/api/novel_view.py`](../../../../fastApi-app/api/novel_view.py)). **Not** part of `/images/click`/`/images/inpaint`.

**Default backend:** **Hunyuan3D-2.1** (`Hunyuan3D2ReconstructionStrategy`), a Hugging Face Space called via `gradio_client`.

**Automatic fallback:** If the primary strategy raises, `Reconstruction3DFacade` retries with **TripoSR** (`TriposrReconstructionStrategy`, local PyTorch, weights `stabilityai/TripoSR`) using identical arguments. If the fallback also raises, the facade re-raises the primary's original exception.

> **The TripoSR fallback is unavailable in the deployed container.** Its `torchmcubes` dependency compiles against torch's CMake config, which demands a full CUDA *toolkit* (`nvcc`, headers) — the `nvidia-*-cu12` runtime libraries bundled in the PyPI torch wheel are not enough — so it cannot build in the slim runtime image without a ~6GB CUDA-devel base. It is therefore omitted from `TestModules/pyproject.toml`'s dependencies.
>
> **All TripoSR code is intact and still supported**; only the package is absent. Nothing imports it at module scope (the import is lazy and guarded inside `_load_tsr_model`), so the sole consequence is that a failure of the primary Hunyuan3D Space backend surfaces as an error instead of silently falling back. Restore it on any machine with the CUDA toolkit with:
>
> ```bash
> pip install "torchmcubes @ git+https://github.com/tatsy/torchmcubes.git"
> ```
>
> No code change is needed — the strategy resumes working on import. See the NOTE in `TestModules/pyproject.toml` and [`docs/deployment/aws-runbook.md`](../../../deployment/aws-runbook.md).

**Alternate backends (not used by default or as fallback):** OpenLRM (`OpenLrmReconstructionStrategy`), Trellis (`TrellisReconstructionStrategy`), and VFusion3D (`Vfusion3dReconstructionStrategy`) — reachable only by injecting a strategy explicitly into `Reconstruction3DFacade(...)`.

**In one line:** Image in → primary strategy (fallback on failure) → GLB out (`bytes`, `Path`, or `BytesIO`).

Code: [`TestModules/src/ai_engines/reconstruction_3d/`](../../../../TestModules/src/ai_engines/reconstruction_3d/).

## Detail pages

- [components.md](components.md) — facade, strategies, helpers, vendored backend path
- [flow.md](flow.md) — Hunyuan3D-2.1/TripoSR/OpenLRM/Trellis execution steps (high level)
- [contracts.md](contracts.md) — flexible inputs, GLB outputs, HTTP boundary
- [operations.md](operations.md) — space/model ids, caches, presets, errors

Parent: [ai-engines/README.md](../README.md).
