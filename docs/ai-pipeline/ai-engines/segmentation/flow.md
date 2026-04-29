# Segmentation execution and data flow

1. Adapter yields 3-channel “RGB-like” tensor from depth + optional RGB reference paths internal to adapter.
2. SAM receives adapted tensor + click point.
3. With `multimask_output=True`, pick **`masks[1]`** as tight candidate (project convention).
4. Optional dilation by `expand_pixels` after routing decision.

Called **twice** per removal: routing probe (`expand_pixels=0`) and final mask with routed expansion.
