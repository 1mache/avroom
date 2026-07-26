# Novel view components

Source: [`TestModules/src/ai_engines/novel_view/`](../../../../TestModules/src/ai_engines/novel_view/).

- **`NovelViewFacade`** — Wraps exactly one `NovelViewStrategy`; forwards `synthesize(...)`. Defaults to `StableZero123NovelViewStrategy`.
- **`NovelViewRotationAdapter`** — Converts optional readable pose directions (`CLOCKWISE` / `C_CLOCKWISE`, `UP` / `DOWN`, `ZOOM_IN` / `ZOOM_OUT`) into signed azimuth, relative elevation, and radius. Exposes named magnitude constants (`SIDE`, `BACK`, `LOW_TILT`, `ZOOM_STEP`, etc.).
- **`NovelViewStrategy`** — ABC for cutout + pose → 2D image backends.
- **`novel_view_preprocess`** — Alpha bbox crop, square pad, model resize, white-bg remask, canvas composite.
- **`StableZero123NovelViewStrategy`** — Default backend: Diffusers `pipeline_zero1to3` on `kxic/stable-zero123`. Raises **`StableZero123NovelViewError`** on inference failures.
- **`to_pil_rgba`** (reused from reconstruction_3d) — Normalizes heterogeneous inputs (bytes, ndarray, PIL, paths).

## HTTP layer (FastAPI)

- **`POST /images/novel-view`** — [`fastApi-app/api/novel_view.py`](../../../../fastApi-app/api/novel_view.py); resolves pose via `NovelViewRotationAdapter` before calling the facade.
- Schemas: `NovelViewRequest`, `NovelViewResponse` in [`fastApi-app/schemas/image.py`](../../../../fastApi-app/schemas/image.py)
- Cutout resolution: `resolve_object_cutout_path` in [`fastApi-app/core/object_storage.py`](../../../../fastApi-app/core/object_storage.py)
- Disk cache: `{uid}_{object_id}_novel_az{azimuth}_el{rel_el}.png` via `object_novel_view_path`
