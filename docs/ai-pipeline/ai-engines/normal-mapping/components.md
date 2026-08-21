# Normal mapping components

Source: [`TestModules/src/ai_engines/normal_mapping/`](../../../../TestModules/src/ai_engines/normal_mapping/).

- **`NormalMappingFacade`** — Single entry used by debug render; forwards to injected `NormalMappingStrategy`. Default strategy is `Metric3DNormalMappingStrategy`.
- **`NormalMappingStrategy`** — ABC with `map_normals(image)`.
- **`Metric3DNormalMappingStrategy`** — Wraps Metric3D v2 via `torch.hub` (`yvanyin/metric3d`). Default hub id `metric3d_vit_small`; also supports `metric3d_vit_large` / `metric3d_vit_giant2`. ConvNeXt hub models have no normals and are rejected at runtime.

Visualization helper (not part of the engine package): `avroom_object_removal.utils.colorize_normals`.
