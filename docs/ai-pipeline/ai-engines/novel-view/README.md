# Novel view synthesis

**What this is:** Novel view of an object cutout at a camera pose. The facade picks a concrete `NovelViewStrategy`. The HTTP layer optionally accepts readable pose directions (`CLOCKWISE`, `UP`, `ZOOM_IN`, …) via `NovelViewRotationAdapter`.

**When it runs:** Direct `NovelViewFacade` calls (smoke tests) or `POST /images/novel-view` (FastAPI).

**Facade default:** **Stable Zero123** (`StableZero123NovelViewStrategy`) — image-to-image diffusion.

**HTTP path:** **Mesh render** (`MeshRenderNovelViewStrategy`) — ensures `tmp/3d/{uid}_{object_id}.glb` (generate if missing), then rasterizes the mesh at the orbit pose. Zero123 is not used by the HTTP route.

**Not the same as:** `Reconstruction3DFacade` / `POST /3d/test-3d` alone (those only produce GLB); novel-view returns a 2D BGRA image.

**In one line:** Cutout (+ optional GLB) + pose → uint8 BGRA `(H, W, 4)` novel-view image.

Code: [`TestModules/src/ai_engines/novel_view/`](../../../../TestModules/src/ai_engines/novel_view/).

## Detail pages

- [components.md](components.md) — facade, strategy, preprocess helpers
- [flow.md](flow.md) — HTTP mesh-render + Stable Zero123 steps
- [contracts.md](contracts.md) — inputs/outputs, optional `mesh=`, HTTP boundary
- [operations.md](operations.md) — Zero123 model id, license, mesh render OpenGL notes

Parent: [ai-engines/README.md](../README.md).
