# Utils operations

## Tunables

- **`expand_mask_uniform` radius** — Default **3** when invoked by orchestrator (matches halo mitigation assumption).
- **`shift_pixels`** downward bias — Helps masks cover occluding pixels lower in frame — inspect [`mask_refiner.py`](../../../TestModules/src/utils/mask_refiner.py).
- **`depth_tolerance`** inside refiner — Meaningful only if `expand_and_clip` participates (currently unused by removal pipeline).

## Debug directory resolution

Saver resolves outputs folder relative to package installation — defaults effectively targeting `TestModules/outputs/` layout.

## Operational caveat

Repeated runs overwrite identical filenames — archival tooling must snapshot external directories between experiments.
