# Novel view synthesis

**What this is:** Optional **image-to-image** novel view synthesis from an object cutout plus camera pose. The facade picks a concrete `NovelViewStrategy`.

**When it runs:** When application code calls `NovelViewFacade` directly (smoke tests) or via `POST /images/novel-view` (FastAPI).

**Default backend:** **Stable Zero123** (`StableZero123NovelViewStrategy`), weights from community Diffusers repo **`kxic/stable-zero123`** (converted from official `stabilityai/stable-zero123` ckpt).

**Not the same as:** `Reconstruction3DFacade` / `POST /3d/test-3d`, which produce GLB meshes for Three.js.

**In one line:** RGBA cutout in → active strategy → RGBA novel-view image out (uint8 `numpy.ndarray`, BGRA channel order).

Code: [`TestModules/src/ai_engines/novel_view/`](../../../../TestModules/src/ai_engines/novel_view/).

## Detail pages

- [components.md](components.md) — facade, strategy, preprocess helpers
- [flow.md](flow.md) — Stable Zero123 execution steps
- [contracts.md](contracts.md) — flexible inputs, RGBA outputs, HTTP boundary
- [operations.md](operations.md) — model id, license, HF auth, VRAM, CFG

Parent: [ai-engines/README.md](../README.md).
