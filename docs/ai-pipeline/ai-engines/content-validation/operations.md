# Content validation operations

## Model

| Setting | Default |
|---------|---------|
| Hugging Face model id | `openai/clip-vit-base-patch32` |
| Load timing | Lazy on first `validate()` call |

## Thresholds (strategy constructor)

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `positive_threshold` | `0.5` | Minimum `P(scene)` from the scene binary contest |
| `negative_threshold` | `0.5` | Maximum allowed `P(bad concept)` from each negative binary contest |

## Inference pool

- Job kind: `VALIDATE_CONTENT`
- Serialized via `JobRequest.image_bytes`
- Uses `inference_session()` lock in inline mode (same as novel-view / 3D facade jobs)

## Debug artifacts

`ContentImageValidator` saves `content_validation_input` via `DebugImageSaver` when debug output is enabled elsewhere in the pipeline.

## Tests

- [`TestModules/tests/test_content_image_validator.py`](../../../../TestModules/tests/test_content_image_validator.py) — stub strategy + monkeypatched CLIP scores
- [`fastApi-app/tests/test_image_validation.py`](../../../../fastApi-app/tests/test_image_validation.py) — technical checks + upload route gates

## FastAPI technical validation env vars

See [`fastApi-app/settings.py`](../../../../fastApi-app/settings.py): `UPLOAD_MIN_BYTES`, `UPLOAD_MAX_BYTES`, `UPLOAD_MIN_WIDTH`, `UPLOAD_MIN_HEIGHT`, `UPLOAD_BLUR_MIN_VARIANCE`, etc.
