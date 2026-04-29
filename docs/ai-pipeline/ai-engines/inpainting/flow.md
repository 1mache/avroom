# Inpainting execution and data flow

1. Align/binarize mask to image dimensions inside hybrid strategy.
2. Run LaMa fill on masked region (mean-fill preprocessing inside LaMa strategy).
3. If SD `strength` exceeds skip threshold (~0.2), run SD inpainting at working resolution then resize back.
4. Align outputs if shapes drift.
5. Apply sharpening + subtle interior color blend toward boundary statistics.

Returns single BGR frame matching input geometry.
