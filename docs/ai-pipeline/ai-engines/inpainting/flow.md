# Inpainting execution and data flow

1. Align/binarize mask to image dimensions inside hybrid strategy.
2. Run LaMa fill on masked region (mean-fill preprocessing inside LaMa strategy).
3. If SD `strength` exceeds skip threshold (~0.2), run SD inpainting at working resolution then resize back.
4. Verify the candidate (`InpaintingVerificationFacade`, CLIP labels on a padded mask crop). Failures replay SD with the returned JSON params up to `INPAINT_VERIFY_MAX_RETRIES` (keep last on exhaust). LaMa-only skip still verifies; a fail starts SD.
5. Align outputs if shapes drift.
6. Apply sharpening + subtle interior color blend toward boundary statistics.
7. **Compose onto original** — `BackgroundInpainter` copies `original_image` and replaces only compose-mask pixels (typically cutout alpha / raw SAM mask) with the model output; non-compose pixels stay unchanged. Inpainting still uses the broader `refined_mask`. Padding is controlled by `COMPOSE_MASK_PADDING_RADIUS`.

Returns single BGR frame matching input geometry.
