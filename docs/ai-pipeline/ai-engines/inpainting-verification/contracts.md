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
    scores: dict[str, float]
    winner_label: str
```

Gemini fail: `param_fixes_json` is rewritten knobs (prompt/negative/strength/steps/guidance). CLIP fallback fail: rewritten prompt + bumped strength (not a no-op replay). Hybrid replays known keys only. Optional `verify_trace` list kwarg on `HybridInpaintingStrategy.inpaint` records each attempt (images + params) for `/debug/inpaint-verify`; production inpaint still returns only the final BGR array.

## Gemini JSON

Required: `ok`. Optional: `winner_label`, `prompt`, `negative_prompt`, `strength`, `num_inference_steps`, `guidance_scale`. Missing knobs copy the input params.

## Labels (CLIP fallback)

Pass when argmax is `a photo of clean seamless floor or wall texture with even lighting`. Fail labels cover leftover shadows and smeared blobs.
