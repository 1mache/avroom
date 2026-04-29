# Segmentation

**What this is:** Turns one click into an object mask using Segment Anything, fed from **adapted depth** so fabric seams do not dominate boundaries.

**When it runs:** After depth exists and routing computed parameters; executes twice (probe + final).

**In one line:** SAM multimask → choose tight mask → optionally dilate per router.

Code: [`TestModules/src/ai_engines/segmentation/`](../../../../TestModules/src/ai_engines/segmentation/).

## Detail pages

- [components.md](components.md) — facade, SAM strategy, adapter
- [flow.md](flow.md) — multimask selection and dilation
- [contracts.md](contracts.md) — inputs and mask semantics
- [operations.md](operations.md) — env vars, checkpoints, debug PNGs

Parent: [ai-engines/README.md](../README.md).
