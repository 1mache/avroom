# Content validation components

Source: [`TestModules/src/ai_engines/content_validation/`](../../../../TestModules/src/ai_engines/content_validation/).

## Facade

- **`ContentValidationFacade`** — Holds one `ContentValidationStrategy`. Default: `CompositeContentValidationStrategy` wrapping `ClipZeroShotContentValidationStrategy`.

## Strategy ABC

- **`ContentValidationStrategy`** — `validate(image: np.ndarray) -> ContentValidationResult`

## Result type

- **`ContentValidationResult`** — frozen dataclass with `is_valid`, `checks`, `scores`, `messages`.

## Concrete strategies

| Strategy | Role |
|----------|------|
| `ClipZeroShotContentValidationStrategy` | CLIP zero-shot labels for scene/person/product/screenshot/obstruction/NSFW/stylization |
| `CompositeContentValidationStrategy` | Merges multiple strategies; `is_valid = all(checks)` |

## Core orchestrator

- **`ContentImageValidator`** ([`TestModules/src/core/content_image_validator.py`](../../../../TestModules/src/core/content_image_validator.py)) — decodes bytes/path to BGR and delegates to the facade. Standalone pre-pipeline gate.

## FastAPI bridge

- [`fastApi-app/core/content_validation.py`](../../../../fastApi-app/core/content_validation.py) — lazy import + `validate_upload_content`
- [`fastApi-app/core/image_validation/`](../../../../fastApi-app/core/image_validation/) — deterministic technical checks (separate from this engine)
