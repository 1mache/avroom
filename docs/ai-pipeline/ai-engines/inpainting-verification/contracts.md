# Inpainting verification contracts

## Input

| Field | Type | Notes |
|-------|------|-------|
| `image` | `np.ndarray` | BGR `uint8` candidate, shape `(H, W, 3)` |
| `mask` | `np.ndarray` | Binary or 0/255, same H/W |
| `params` | `InpaintSdParams` | SD knobs for this candidate |
| `original_image` | `np.ndarray \| None` | Pre-inpaint scene; Gemini dual-crop when provided |

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

Trace entries may include:

| Field | Meaning |
|-------|---------|
| `verify_original_crop_bgr` | Original scene in the same window as the verifier crop |
| `clip_crop_bgr` | Outlined candidate crop (what Gemini sees as image 2) |

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

Dual-crop input: original crop + outlined candidate crop of the **same** window. The cyan outline marks the inpaint region on image 2. Minimum crop size is enforced via `MIN_VERIFY_CROP_PX` / `MIN_VERIFY_CROP_FRAC`.

## Post-verify logging

After each Gemini attempt, one INFO line records `ok`, `winner`, model id, crop size, window bounds, mask pixel count inside the window, `dual_crop`, strength, dilate fields, and on fail the next retry recipe (`next_strength`, `next_mask_dilate`, `next_compose_dilate`, truncated prompt). Hybrid logs `attempt_index`, `mask_px`, and the same retry fields on fail. CLIP fallback logs reason plus top label/score.

## Labels (CLIP fallback)

Pass when argmax is `a photo of clean seamless floor or wall texture with even lighting`. Fail labels cover leftover shadows and smeared blobs. On fail, CLIP uses fixed dilate heuristics (`10` / `8` px) when Gemini is unavailable.
