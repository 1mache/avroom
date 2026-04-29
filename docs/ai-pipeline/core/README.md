# Core

**What this is:** One entry point (`ObjectRemover`) that runs the click-to-remove pipeline end to end and returns the two images FastAPI expects.

**When it runs:** On every `/images/click` through [`image_processing.segment_at_click`](../../../fastApi-app/core/image_processing.py), and from manual test scripts.

**In one line:** Decode image, map depth, adapt for SAM, route parameters, segment, refine mask, inpaint, build BGRA cutout.

Code: [`TestModules/src/core/`](../../../TestModules/src/core/).

## Detail pages

- [components.md](components.md) — orchestrator, helpers, wiring, coupling
- [flow.md](flow.md) — stage order and data threading
- [contracts.md](contracts.md) — `remove_object` inputs and return tuple
- [operations.md](operations.md) — knobs, caches, debug files, failure notes

Related: [AI engines](../ai-engines/README.md) (depth, segmentation, inpainting), [routing](../routing/README.md), [utils](../utils/README.md).
