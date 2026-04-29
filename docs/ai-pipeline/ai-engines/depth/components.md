# Depth components

Source: [`TestModules/src/ai_engines/depth/`](../../../../TestModules/src/ai_engines/depth/).

- **`DepthMappingFacade`** — Single entry used by core; forwards to injected `DepthMappingStrategy`.
- **`DepthMappingStrategy`** — ABC with `map_depth(image)`.
- **`DepthAnythingMappingStrategy`** — Wraps one HF depth pipeline by model id.
- **`NearFarBlendedDepthMappingStrategy`** — Default composition: runs near + far `DepthAnythingMappingStrategy`, normalizes both to 0–255, alpha-blends using near-map values as weights.
