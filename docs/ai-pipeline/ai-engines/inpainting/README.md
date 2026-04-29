# Inpainting

**What this is:** Fills the masked hole left after segmentation so the wall/floor reads naturally.

**When it runs:** After mask refinement in core, before BGRA cutout composition.

**In one line:** LaMa does bulk structure; Stable Diffusion optionally refines texture when strength is high enough.

Code: [`TestModules/src/ai_engines/inpainting/`](../../../../TestModules/src/ai_engines/inpainting/).

## Detail pages

- [components.md](components.md) — facade and strategies
- [flow.md](flow.md) — LaMa → optional SD → blend
- [contracts.md](contracts.md) — image/mask IO
- [operations.md](operations.md) — thresholds, SD defaults, debug PNGs

Parent: [ai-engines/README.md](../README.md).
