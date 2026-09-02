# Normal mapping

**What this is:** Per-pixel surface-normal estimation from a single room photo (camera-frame unit vectors).

**When it runs:** Cached on upload and `POST /images/{uid}/warm-maps` when `NORMAL_MAP=true` (default). Used by smart-paste auto-rotate (normal sampling at cutout center vs drop point). Also exposed for inspection via `POST /debug/normal-map` and the DebugScreen normal-map panel.

**In one line:** Metric3D v2 (ViT hub) predicts float normals; `colorize_normals` turns them into a viewable PNG.

Code: [`TestModules/src/ai_engines/normal_mapping/`](../../../../TestModules/src/ai_engines/normal_mapping/).

## Detail pages

- [components.md](components.md) — facade and strategies
- [flow.md](flow.md) — preprocess → inference → unpad/resize
- [contracts.md](contracts.md) — input/output arrays
- [operations.md](operations.md) — hub model ids, caching, deps

Parent: [ai-engines/README.md](../README.md).
