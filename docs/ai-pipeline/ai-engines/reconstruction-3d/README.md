# Reconstruction 3D

**What this is:** Optional mesh generation from the cutout image via Trellis on Hugging Face Spaces.

**When it runs:** Only when application code calls `Reconstruction3DFacade` directly (smoke tests today). **Not** part of `/images/click`.

**In one line:** Image → queued Space job → downloadable GLB.

Code: [`TestModules/src/ai_engines/reconstruction_3d/`](../../../../TestModules/src/ai_engines/reconstruction_3d/).

## Detail pages

- [components.md](components.md) — facade, Trellis strategy, quality presets
- [flow.md](flow.md) — Space calls sequence
- [contracts.md](contracts.md) — flexible inputs, GLB outputs
- [operations.md](operations.md) — Space id, presets, errors

Parent: [ai-engines/README.md](../README.md).
