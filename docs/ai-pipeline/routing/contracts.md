# Routing contracts

Return payload keys consumed by [`object_remover.py`](../../../TestModules/src/core/object_remover.py):

- **`input_image`** — Enum/string selecting which tensor feeds SAM for final pass (`adapted_depth` in production routing output).
- **`expand_pixels`** — Integer dilation applied after SAM tight mask selection.
- **`sd_strength`** — Float forwarded as inpainting strength (hybrid interprets threshold rules).
- **`use_broad_mask`** — Boolean controlling segmentation strategy branch.

Adding keys requires simultaneous orchestrator updates — treat return dict as stable API surface between routing package and core.
