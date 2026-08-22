# AI Engines

**What this is:** Model-facing subsystems grouped under [`TestModules/src/ai_engines/`](../../../TestModules/src/ai_engines/). Each domain exposes a facade and hides a strategy implementation.

**When they run:** Depth, segmentation, and inpainting run inside every `ObjectRemover.remove_object` call. Reconstruction 3D runs from `POST /3d/test-3d` and `POST /images/novel-view` — not from `/images/click`.

**In one line:** Facades wrap strategies so checkpoints and inference details can change without rewriting the orchestrator.

## Detail pages (cross-cutting)

- [components.md](components.md) — facade list and ABCs
- [flow.md](flow.md) — shared call pattern
- [contracts.md](contracts.md) — facade vs strategy responsibilities
- [operations.md](operations.md) — caching model and debug boundaries

## Per-domain overviews

| Domain | Overview |
|--------|----------|
| [depth/README.md](depth/README.md) | Two depth nets blended into one map |
| [segmentation/README.md](segmentation/README.md) | SAM on adapted depth, point prompt |
| [inpainting/README.md](inpainting/README.md) | LaMa hole fill, optional SD polish |
| [reconstruction-3d/README.md](reconstruction-3d/README.md) | Image-to-GLB (Hunyuan3D-2.1 default, automatic TripoSR fallback; OpenLRM/Trellis/VFusion3D optional) |
| [content-validation/README.md](content-validation/README.md) | Upload content suitability (CLIP zero-shot default) |

Upstream: [core/README.md](../core/README.md).
