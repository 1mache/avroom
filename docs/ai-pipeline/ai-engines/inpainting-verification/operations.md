# Inpainting verification operations

## Constants (`HybridInpaintingStrategy`)

| Name | Default | Meaning |
|------|---------|---------|
| `INPAINT_VERIFY_MAX_RETRIES` | `2` | SD retries after the first candidate (3 SD calls max when SD ran first) |
| `INPAINT_VERIFY_CROP_PAD_RATIO` | `0.25` | Pad mask bbox on each side before verify |

## Gemini

REST `generateContent`. Model id comes from `GEMINI_MODEL` in `fastApi-app/.env` on every verify (default `gemini-2.5-flash-lite`; `gemini-2.0-flash` is shut down). Auth: `x-goog-api-key` header. Key: `GEMINI_API_KEY`. Unrestricted Cloud keys return 403 as of June 2026 — restrict the key to the Generative Language API or mint one in AI Studio. Inject `complete_fn` in tests; do not call the network in unit tests.

## CLIP fallback

Reuses `openai/clip-vit-base-patch32` via content-validation `score_labels`. Inject `score_fn` in tests; do not load CLIP in unit tests.

## Tests

- [`TestModules/tests/test_inpainting_verification.py`](../../../../TestModules/tests/test_inpainting_verification.py)
