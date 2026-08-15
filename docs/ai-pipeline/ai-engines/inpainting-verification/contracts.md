# Inpainting verification contracts

## Input

| Field | Type | Notes |
|-------|------|-------|
| `image` | `np.ndarray` | BGR `uint8` candidate, shape `(H, W, 3)` |
| `mask` | `np.ndarray` | Binary or 0/255, same H/W |
| `params` | `InpaintSdParams` | SD knobs for this candidate |

## Output

```python
@dataclass(frozen=True)
class InpaintingVerificationResult:
    ok: bool
    param_fixes_json: str
```

CLIP v1 fail: `param_fixes_json == params.to_json()`. Hybrid replays known keys only.

## Labels (CLIP default)

Pass when argmax is `photorealistic room`. Other labels: `smeared blob`, `unrealistic shaped object`.
