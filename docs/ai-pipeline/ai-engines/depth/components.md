# Depth components

Source: [`TestModules/src/ai_engines/depth/`](../../../../TestModules/src/ai_engines/depth/).

- **`DepthMappingFacade`** — Single entry used by core; forwards to injected `DepthMappingStrategy`. Default strategy is `EnhancedEdgeDepthMappingStrategy`.
- **`DepthMappingStrategy`** — ABC with `map_depth(image)`.
- **`DepthAnythingMappingStrategy`** — Wraps one HF depth pipeline by model id.
- **`NearFarBlendedDepthMappingStrategy`** — Runs near + far `DepthAnythingMappingStrategy`, normalizes both to 0–255, alpha-blends using near-map values as weights. Used as the inner blending layer by `EnhancedEdgeDepthMappingStrategy`.
- **`EnhancedEdgeDepthMappingStrategy`** — **Default strategy.** Wraps `NearFarBlendedDepthMappingStrategy` and applies two post-processing steps to sharpen object-floor separation: (1) CLAHE (`clipLimit=2.0`, tile grid `8×8`) boosts local contrast at contact boundaries; (2) bilateral filter (`d=9`, `sigmaColor=75`, `sigmaSpace=75`) smooths intra-surface depth while preserving high-gradient silhouette edges. Processing order — CLAHE then bilateral — is intentional.
