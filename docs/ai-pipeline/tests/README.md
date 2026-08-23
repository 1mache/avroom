# Tests

**What this is:** Manual Python harnesses around `avroom_object_removal`, not automated pytest coverage.

**When they run:** On developer machines when validating depth upgrades, segmentation tweaks, inpainting thresholds, or non-default 3D reconstruction backends (OpenLRM / Trellis / VFusion3D — the facade's default Hunyuan3D-2.1 and its TripoSR fallback are exercised through the running FastAPI server instead, see `POST /3d/test-3d`).

**In one line:** Point scripts at sample imagery and inspect dumped PNGs or GLBs.

Code: [`TestModules/tests/`](../../../TestModules/tests/).

## Detail pages

- [components.md](components.md) — script inventory
- [flow.md](flow.md) — typical local workflow
- [contracts.md](contracts.md) — informal expectations
- [operations.md](operations.md) — env + runtime caveats

Related: [core/README.md](../core/README.md), [ai-engines/reconstruction-3d/README.md](../ai-engines/reconstruction-3d/README.md).
