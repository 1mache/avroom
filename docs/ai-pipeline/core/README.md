# Core

**What this is:** Three focused entry points covering the full click-to-remove pipeline and its composable sub-steps.

| Class | Responsibility |
|---|---|
| `ObjectRemover` | End-to-end orchestrator. Runs all 7 stages and returns `(background_bgr, cutout_bgra)`. Used by FastAPI. |
| `ObjectSegmentor` | Stages 1–3 + 5–7 (no inpainting). Returns every SAM candidate as `(refined_mask, cutout_bgra)` pairs. |
| `BackgroundInpainter` | Stage 4 only. Accepts an original image + mask and returns the inpainted background. |

**When it runs:** `ObjectSegmentor` runs on `/images/segment`, then `BackgroundInpainter` runs on `/images/inpaint` after user mask choice. `ObjectRemover` remains for legacy `/images/click` and manual test scripts.

Code: [`TestModules/src/core/`](../../../TestModules/src/core/).

## Detail pages

- [components.md](components.md) — orchestrators, helpers, wiring, coupling
- [flow.md](flow.md) — stage order and data threading for each entry point
- [contracts.md](contracts.md) — signatures and return types
- [operations.md](operations.md) — knobs, caches, debug files, failure notes

Related: [AI engines](../ai-engines/README.md) (depth, segmentation, inpainting), [routing](../routing/README.md), [utils](../utils/README.md).
