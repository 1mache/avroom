# Content validation contracts

## Input

| Field | Type | Notes |
|-------|------|-------|
| `image` | `np.ndarray` | BGR `uint8`, shape `(H, W, 3)` |

FastAPI passes raw upload bytes; `ContentImageValidator` decodes via OpenCV before calling the facade.

## Output

```python
@dataclass(frozen=True)
class ContentValidationResult:
    is_valid: bool
    checks: dict[str, bool]
    scores: dict[str, float]
    messages: tuple[str, ...]
```

## Check keys (CLIP default strategy)

| Key | Pass when |
|-----|-----------|
| `scene_space_or_landscape` | Room/landscape positive labels beat person/product negatives |
| `not_person_centric` | Person/portrait/selfie score below threshold |
| `not_product_shot` | Product/studio single-object score below threshold |
| `not_screenshot` | Screenshot/UI score below threshold |
| `not_obstructed` | Hand/lens obstruction score below threshold |
| `not_nsfw` | NSFW label score below threshold |
| `not_heavily_stylized` | Painting/anime/filter score below threshold |

## HTTP mapping

- Any failed check → `POST /images/upload` returns **422** with joined `messages`.
- Success response shape unchanged (`ImageUploadResponse`).

## Technical checks (FastAPI only)

Handled by [`fastApi-app/core/image_validation/`](../../../../fastApi-app/core/image_validation/) before content validation runs. See backend [data-flow.md](../../../backend/data-flow.md).
