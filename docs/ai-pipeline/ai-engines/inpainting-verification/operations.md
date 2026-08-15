# Inpainting verification operations

## Constants (`HybridInpaintingStrategy`)

| Name | Default | Meaning |
|------|---------|---------|
| `INPAINT_VERIFY_MAX_RETRIES` | `2` | SD retries after the first candidate (3 SD calls max when SD ran first) |
| `INPAINT_VERIFY_CROP_PAD_RATIO` | `0.25` | Pad mask bbox on each side before CLIP |

## CLIP

Reuses `openai/clip-vit-base-patch32` via content-validation `score_labels`. Inject `score_fn` in tests; do not load CLIP in unit tests.

## Tests

- [`TestModules/tests/test_inpainting_verification.py`](../../../../TestModules/tests/test_inpainting_verification.py)
