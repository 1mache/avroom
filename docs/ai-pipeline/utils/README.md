# Utils

**What this is:** Shared image helpers — mask morphology, debug dumps, cutout RGBA composition — reused by core and strategies.

**When they run:** Throughout segmentation refinement and orchestrator terminal composition stages.

**In one line:** Keep numpy masks sane before inpainting and package pixels for frontend overlay previews.

Code: [`TestModules/src/utils/`](../../../TestModules/src/utils/).

## Detail pages

- [components.md](components.md) — classes list
- [flow.md](flow.md) — who calls what
- [contracts.md](contracts.md) — IO shapes
- [operations.md](operations.md) — radius bias, outputs folder behavior

Related: [core/README.md](../core/README.md).
