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

Each check is a 2-label softmax: concept vs a concrete room/space alternative.

| Key | Pass when |
|-----|-----------|
| `scene_space_or_landscape` | `P(indoor room or outdoor space) >= positive_threshold` |
| `not_person_centric` | `P(person/selfie/portrait) < negative_threshold` |
| `not_product_shot` | `P(product on plain background) < negative_threshold` |
| `not_screenshot` | `P(screenshot or screen photo) < negative_threshold` |
| `not_obstructed` | `P(hand/body blocking camera) < negative_threshold` |
| `not_nsfw` | `P(explicit NSFW/nude) < negative_threshold` |
| `not_heavily_stylized` | `P(anime/painting/cartoon/filtered) < negative_threshold` |

## HTTP mapping

- Any failed check → `POST /images/upload` returns **422** with joined `messages`.
- Success response shape unchanged (`ImageUploadResponse`).

## Technical checks (FastAPI only)

Handled by [`fastApi-app/core/image_validation/`](../../../../fastApi-app/core/image_validation/) before content validation runs. See backend [data-flow.md](../../../backend/data-flow.md).
