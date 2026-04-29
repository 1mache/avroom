# 3D Reconstruction (Hunyuan3D-2.1) — Stub

> **Status:** **Not wired into the pipeline.** This document exists so the workstream is tracked; do not assume any code under this path runs at request time.

## Where it lives

[`TestModules/src/ai_engines/3dRreconstruction/Hunyuan3D-2.1/`](../../TestModules/src/ai_engines/3dRreconstruction/Hunyuan3D-2.1/)

It is an upstream Tencent Hunyuan3D-2.1 checkout (visible only via its `.git/` metadata referencing `Tencent/Hunyuan3D-2.1`). There are no Python files added by this project on top of it, and no Python wrapper around it inside `avroom_object_removal`.

## What is/isn't wired in

A quick check confirms:

- [`TestModules/src/__init__.py`](../../TestModules/src/__init__.py) exports `ObjectRemover` only.
- [`TestModules/src/core/objectRemover.py`](../../TestModules/src/core/objectRemover.py) does not import anything from `3dRreconstruction/`.
- The package list in [`TestModules/pyproject.toml`](../../TestModules/pyproject.toml) lines 12–21 does not include any `3d` or `hunyuan` subpackage.

If the file ever gets used at runtime, that fact will need to be reflected in [object-remover.md](object-remover.md) — and this stub should be replaced with a real architecture page.

## Intent

The folder name `3dRreconstruction` (and the Hunyuan3D-2.1 checkout) suggests a future capability where, after object removal, the pipeline could reconstruct a 3D model of the removed object (or of the room) — useful for AR/VR inspection, virtual staging, or for repositioning the cutout in space.

That work is **not started in this repo**. There is no integration glue, no public API, no tests.

## What to do if you want to integrate it

1. Decide on a Python wrapper (likely a new `HunyuanFacade` under `ai_engines/3dRreconstruction/`).
2. Define the input/output contract — probably `image (BGR or RGB) -> mesh (.glb / .obj / point cloud)`.
3. Add a new pipeline stage in `ObjectRemover` (or, more likely, a separate top-level entry point so the click-to-segment path stays cheap).
4. Decide on storage for produced 3D assets (the FastAPI side currently has no concept of non-image outputs).
5. Update [overview.md](overview.md), [object-remover.md](object-remover.md), and the top-level [../architecture.md](../architecture.md) accordingly.

Until any of that happens, the folder should be treated as a vendored upstream snapshot only.
