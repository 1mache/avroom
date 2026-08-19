# Inpainting verification components

Source: [`TestModules/src/ai_engines/inpainting_verification/`](../../../../TestModules/src/ai_engines/inpainting_verification/).

## Facade

- **`InpaintingVerificationFacade`** — Holds one `InpaintingVerificationStrategy`. Default: `GeminiInpaintingVerificationStrategy`.

## Strategy ABC

- **`InpaintingVerificationStrategy`** — `verify(image, mask, params, *, original_image=None) -> InpaintingVerificationResult`

## Result and params

- **`InpaintingVerificationResult`** — `ok`, `param_fixes_json`, `scores`, `winner_label`.
- **`InpaintSdParams`** — SD knobs plus verifier retry directives `mask_dilate_pixels` / `compose_dilate_pixels` (AI-decided on fail, `0` on pass). `to_json` / `from_json` with safety caps via `clamp_dilate_fields`.

## Crop helpers

| Symbol | Role |
|--------|------|
| `CropWindow` | Frozen `(y0, y1, x0, x1)` slice |
| `mask_crop_window` | Mask bbox + pad, optional minimum side |
| `crop_with_window` | Slice BGR array |
| `draw_mask_outline` | Cyan contour on candidate crop |
| `build_verify_crops` | Original + outlined candidate in one window |
| `crop_around_mask` | CLIP path; pad only, no minimum size |
| `MIN_VERIFY_CROP_PX` / `MIN_VERIFY_CROP_FRAC` | Gemini minimum crop (256 px / 25%) |
| `GEMINI_CROP_PAD_RATIO` | 0.35 pad for Gemini |

## Concrete strategies

| Strategy | Role |
|----------|------|
| `GeminiInpaintingVerificationStrategy` | Sends original + outlined candidate PNGs + params JSON to Gemini REST. Fail JSON carries rewritten knobs plus AI-decided dilate fields. Logs crop/window/retry recipe at INFO. Placeholder key / HTTP / bad JSON → CLIP. |
| `ClipLabelInpaintingVerificationStrategy` | CLIP softmax over clean texture vs leftover-shadow / smear labels. Fail JSON bumps strength, appends shadow-avoidance text, and uses fixed dilate heuristics. Ignores `original_image`. |
