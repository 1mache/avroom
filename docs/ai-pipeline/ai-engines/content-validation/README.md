# Content validation

**What this is:** ML-based upload content validation for room/landscape suitability. The facade picks a concrete `ContentValidationStrategy`. Default backend is CLIP zero-shot classification.

**When it runs:** On `POST /images/upload` after FastAPI technical validation passes, via `ContentImageValidator` and the inference pool `VALIDATE_CONTENT` job.

**Not wired into:** `ObjectRemover`, `ObjectSegmentor`, or `BackgroundInpainter`.

**In one line:** BGR room photo in → active strategy → `ContentValidationResult` (pass/fail + checks + messages).

Code: [`TestModules/src/ai_engines/content_validation/`](../../../../TestModules/src/ai_engines/content_validation/).

## Detail pages

- [components.md](components.md) — facade, strategy, result type
- [flow.md](flow.md) — CLIP zero-shot execution steps
- [contracts.md](contracts.md) — input/output shapes and check keys
- [operations.md](operations.md) — model id, thresholds, env vars

Parent: [ai-engines/README.md](../README.md).
