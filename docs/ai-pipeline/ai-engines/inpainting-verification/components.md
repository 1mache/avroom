# Inpainting verification components

Source: [`TestModules/src/ai_engines/inpainting_verification/`](../../../../TestModules/src/ai_engines/inpainting_verification/).

## Facade

- **`InpaintingVerificationFacade`** — Holds one `InpaintingVerificationStrategy`. Default: `GeminiInpaintingVerificationStrategy`.

## Strategy ABC

- **`InpaintingVerificationStrategy`** — `verify(image, mask, params) -> InpaintingVerificationResult`

## Result and params

- **`InpaintingVerificationResult`** — `ok`, `param_fixes_json`, `scores`, `winner_label`.
- **`InpaintSdParams`** — `prompt`, `negative_prompt`, `strength`, `num_inference_steps`, `guidance_scale` with `to_json` / `from_json` (unknown keys dropped).

## Crop helper

- **`crop_around_mask`** — bbox of the mask, padded by `INPAINT_VERIFY_CROP_PAD_RATIO` (0.25) on each side, clamped to the image.

## Concrete strategies

| Strategy | Role |
|----------|------|
| `GeminiInpaintingVerificationStrategy` | Sends pad-crop PNG + params JSON to Gemini REST. Fail JSON carries rewritten knobs. Placeholder key / HTTP / bad JSON → CLIP. |
| `ClipLabelInpaintingVerificationStrategy` | CLIP softmax over clean texture vs leftover-shadow / smear labels. Fail JSON bumps strength and appends shadow-avoidance prompt text. |
