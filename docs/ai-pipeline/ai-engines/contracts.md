# AI Engines contracts

## Facade responsibility

Each facade exposes a **small method surface** (e.g. `map_depth`, `get_mask_at_point`, `inpaint`, `generate`) so core and routers depend on stable names, not on HF/SAM/Trellis internals.

## Strategy swap rule

Replacing a strategy means implementing the matching ABC and passing an instance into the facade constructor (or composing strategies inside another strategy, as with hybrid inpainting and near/far depth).

## Outputs into core

- Depth: single-channel uint8 depth map.
- Segmentation: 2D mask aligned with image dimensions.
- Inpainting: BGR image same size as input scene.

Reconstruction 3D returns GLB bytes/path/stream per its strategy — not consumed by FastAPI click handler today.
