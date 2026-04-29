# Routing execution and data flow

1. Provide RGB scene (informational), raw depth, adapted depth, click `(x, y)`.
2. Ask segmentation for tight probe mask (`expand_pixels=0`).
3. Morphologically derive boundary ring around probe mask (kernel size fixed in strategy).
4. Collect depth samples along ring; compute variance statistic vs configured threshold.
5. Branch flat-like vs 3D-like contexts → compute integer `expand_pixels` formula segments.
6. Emit dict containing **`input_image`** selection (production keeps **`adapted_depth`**), **`sd_strength`**, **`use_broad_mask`**, **`expand_pixels`**.

Downstream core reads dict keys verbatim when invoking segmentation/inpainting.
