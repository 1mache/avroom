# AI Engines contracts

## Facade responsibility

Each facade exposes a **small method surface** (e.g. `map_depth`, `get_mask_at_point`, `inpaint`, `generate`) so core and routers depend on stable names, not on HF/SAM/`gradio_client` internals.

## Strategy swap rule

Replacing a strategy means implementing the matching ABC and passing an instance into the facade constructor (or composing strategies inside another strategy, as with hybrid inpainting and near/far depth).

## Outputs into core

- Depth: single-channel uint8 depth map.
- Segmentation: `(expanded_mask, original_mask)` tuple of 2D masks aligned with image dimensions. `expanded_mask` is the SAM output after any `expand_pixels` dilation; `original_mask` is the raw model output.
- Inpainting: BGR image same size as input scene.

Reconstruction 3D returns GLB bytes/path/stream per its strategy — consumed by `POST /3d/test-3d` and `POST /images/novel-view`, not by the click/inpaint handlers.
