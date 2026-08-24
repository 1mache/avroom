# Novel view components

Source: [`TestModules/src/ai_engines/novel_view/`](../../../../TestModules/src/ai_engines/novel_view/).

- **`NovelViewFacade`** — Wraps exactly one `NovelViewStrategy`; forwards `synthesize(...)`. Defaults to `StableZero123NovelViewStrategy`.
- **`NovelViewRotationAdapter`** — Converts optional readable pose directions (`CLOCKWISE` / `C_CLOCKWISE`, `UP` / `DOWN`, `ZOOM_IN` / `ZOOM_OUT`) into signed azimuth, relative elevation, and radius. Exposes named magnitude constants (`SIDE`, `BACK`, `LOW_TILT`, `ZOOM_STEP`, etc.).
- **`NovelViewStrategy`** — ABC for cutout + pose → 2D image backends; optional `mesh=` for GLB-aware strategies.
- **`novel_view_preprocess`** — Alpha bbox crop, square pad, model resize, white-bg remask, canvas composite.
- **`StableZero123NovelViewStrategy`** — Diffusers `pipeline_zero1to3` on `kxic/stable-zero123` (facade default). Ignores `mesh=`. Raises **`StableZero123NovelViewError`** on inference failures.
- **`MeshRenderNovelViewStrategy`** — Photoshop-style mesh rasterization via trimesh + pyrender. Requires `mesh=` (GLB path/bytes) or an injected `Reconstruction3DFacade` fallback. Raises **`MeshRenderNovelViewError`**. Used by the FastAPI novel-view job.
- **`to_pil_rgba`** (reused from reconstruction_3d) — Normalizes heterogeneous inputs (bytes, ndarray, PIL, paths).

## HTTP layer (FastAPI)

- **`POST /images/novel-view`** — [`fastApi-app/api/novel_view.py`](../../../../fastApi-app/api/novel_view.py); resolves pose via `NovelViewRotationAdapter`, ensures the GLB (`core/object_3d.py::ensure_object_glb`), and mesh-renders via the inference pool. No disk cache — every call renders the exact requested pose fresh.
- Schemas: `NovelViewRequest`, `NovelViewResponse` in [`fastApi-app/schemas/novel_view.py`](../../../../fastApi-app/schemas/novel_view.py)
- Cutout resolution: `resolve_object_cutout_path` in [`fastApi-app/core/object_storage.py`](../../../../fastApi-app/core/object_storage.py)
- GLB resolution: `resolve_object_glb_path` / `object_glb_path`; generate via `run_generate_3d` on miss
