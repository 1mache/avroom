# Elevation estimation

**What this is:** Object-centric source elevation for Zero123 novel-view synthesis. Uses depth + mask back-projection with optional GeoCalib gravity/intrinsics.

**When it runs:** At inpaint/object creation in `build_object_metadata_for_inpaint`.

**In one line:** depth + mask + cached calib → `elevation_deg` stored on object metadata.

Code: [`TestModules/src/ai_engines/elevation_estimation/`](../../../../TestModules/src/ai_engines/elevation_estimation/).

## Detail pages

- [components.md](components.md)
- [flow.md](flow.md)
- [contracts.md](contracts.md)
- [operations.md](operations.md)

Parent: [ai-engines/README.md](../README.md).
