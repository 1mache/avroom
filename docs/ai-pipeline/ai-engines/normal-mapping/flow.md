# Normal mapping execution and data flow

1. Decode BGR `uint8` HxWx3 (same as depth).
2. Convert to RGB; keep-ratio resize into Metric3D ViT canvas `(616, 1064)`; pad with ImageNet mean RGB; normalize.
3. `model.inference({'input': tensor})` → take `prediction_normal[:, :3]` (discard depth).
4. Unpad, bilinear-resize to original HxW, L2-normalize → `float32` HxWx3.
5. Debug path only: `colorize_normals` → PNG for the DebugScreen; click samples recover approximate floats from 8-bit RGB.
