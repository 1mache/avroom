# Utils execution and data flow

Typical interactions:

1. **Segmentation** — Calls `MaskRefiner.dilate_mask` when expanding SAM outputs according to routing integers.
2. **Core** — Calls `expand_mask_uniform` after tight mask acceptance to prevent inpainting halo bleed.
3. **Composer** — Reads refined binary mask plus original BGR frame → emits RGBA tensor with cleared alpha outside mask footprint.
4. **Debug saver** — Invoked whenever diagnostics enabled inside orchestrator/strategies.

Utilities remain side-effect limited except debug saver touching filesystem.
