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

Gemini fail: `param_fixes_json` is rewritten knobs plus AI-decided dilation fields. CLIP fallback fail: rewritten prompt + bumped strength + fixed dilate heuristics. Hybrid replays known keys only. Optional `verify_trace` list kwarg on `HybridInpaintingStrategy.inpaint` records each attempt (images + params) for `/debug/inpaint-verify`; production inpaint still returns only the final BGR array.

Optional `inpaint_out: dict` kwarg on `HybridInpaintingStrategy.inpaint` is filled on completion with `verification_ok`, cumulative `compose_dilate_pixels`, and `final_inpaint_mask` for `BackgroundInpainter` paste-back.

## InpaintSdParams JSON

SD knobs: `prompt`, `negative_prompt`, `strength`, `num_inference_steps`, `guidance_scale`.

Verifier retry directives (AI-decided on fail, must be `0` on pass):

| Field | Meaning |
|-------|---------|
| `mask_dilate_pixels` | Uniform dilation of the inpaint mask before the next LaMa+SD pass (`0` = do not expand) |
| `compose_dilate_pixels` | Dilation of the paste mask (cutout alpha) when committing to canvas (`0` = no widen) |

Hybrid applies exactly what the verifier returns; safety caps (`MAX_MASK_DILATE_PER_RETRY`, `MAX_COMPOSE_DILATE_PER_RETRY`, `MAX_CUMULATIVE_MASK_DILATE`) clamp outliers only.

## Gemini JSON

Required: `ok`. Optional: `winner_label`, SD knobs, `mask_dilate_pixels`, `compose_dilate_pixels`. Missing knobs copy the input params; missing dilate fields default to `0`.

## Labels (CLIP fallback)

Pass when argmax is `a photo of clean seamless floor or wall texture with even lighting`. Fail labels cover leftover shadows and smeared blobs. On fail, CLIP uses fixed dilate heuristics (`10` / `8` px) when Gemini is unavailable.
