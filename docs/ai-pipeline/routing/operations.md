# Routing operations

## Thresholds and morphology

- **`DEFAULT_BOUNDARY_VAR_THRESH`** — Variance cutoff distinguishing regimes (see constant in [`boundary_variance_routing_strategy.py`](../../../TestModules/src/routing/strategies/boundary_variance_routing_strategy.py)).
- Boundary ring dilation kernel **7×7** — influences thickness of sampled contour band.

## Expansion formulas

Strategy computes auxiliary scalar **depth_ratio** then applies branch-specific affine sums:

- **3D-like:** `base_expand + int(depth_ratio * secondary_factor_large)`
- **Flat-like:** smaller base expand + scaled secondary factor

Exact literals appear next to constants inside strategy module — consult source before tuning docs.

## Production defaults embedded in routing outcome

Typical stabilized outputs:

- **`sd_strength = 0.35`**
- **`use_broad_mask = False`**
- **`input_image` selecting adapted depth tensor**

## Operational caveat

Probe segmentation writes SAM debug PNGs identical filenames as final pass — debugging interprets latest overwrite only.
