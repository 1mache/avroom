# Routing

**What this is:** Chooses segmentation dilation and inpainting strength using depth geometry near the clicked object boundary.

**When it runs:** After depth adaptation, before final SAM mask inside `remove_object`.

**In one line:** Probe tiny mask → measure depth variance on its contour → decide expand pixels and SD strength.

Code: [`TestModules/src/routing/`](../../../TestModules/src/routing/).

## Detail pages

- [components.md](components.md) — strategies and facade coupling
- [flow.md](flow.md) — probe ring and branching
- [contracts.md](contracts.md) — `run_context` keys
- [operations.md](operations.md) — thresholds, kernels, formulas

Upstream: [core/README.md](../core/README.md). Downstream: [segmentation](../ai-engines/segmentation/README.md), [inpainting](../ai-engines/inpainting/README.md).
