# Reconstruction 3D

**What this is:** Optional **image-to-GLB** mesh generation from a cutout (or any image `to_pil_rgba` accepts). The facade picks a concrete `Reconstruction3DStrategy`.

**When it runs:** Only when application code calls `Reconstruction3DFacade` directly (smoke tests today). **Not** part of `/images/click`.

**Default backend:** Local **OpenLRM** v1.0 (`OpenLrmReconstructionStrategy`), checkpoint `zxhezexin/openlrm-small-obj-1.0` (see [operations.md](operations.md) for weights cache and dependencies).

**Alternate backend:** **Trellis 2** on Hugging Face Spaces via `gradio_client` when you construct `Reconstruction3DFacade(TrellisReconstructionStrategy())`.

**In one line:** Image in → active strategy → GLB out (`bytes`, `Path`, or `BytesIO`), never wired into the HTTP JSON flow today.

Code: [`TestModules/src/ai_engines/reconstruction_3d/`](../../../../TestModules/src/ai_engines/reconstruction_3d/).

## Detail pages

- [components.md](components.md) — facade, strategies, helpers, vendored backend path
- [flow.md](flow.md) — OpenLRM vs Trellis execution steps
- [contracts.md](contracts.md) — flexible inputs, GLB outputs, HTTP boundary
- [operations.md](operations.md) — model id, caches, presets, errors

Parent: [ai-engines/README.md](../README.md).
