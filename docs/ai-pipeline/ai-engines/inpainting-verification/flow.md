# Inpainting verification flow

```mermaid
sequenceDiagram
    participant BG as BackgroundInpainter
    participant Hybrid as HybridInpaintingStrategy
    participant Lama as LamaStrategy
    participant SD as StableDiffusionStrategy
    participant Crop as crop.py
    participant Verifier as InpaintingVerificationFacade
    participant Gemini as GeminiStrategy

    BG->>Hybrid: inpaint refined_mask
    Hybrid->>Lama: structural fill
    alt strength greater than skip threshold
        Hybrid->>SD: first SD pass
    end
    loop until ok or retries exhausted
        Hybrid->>Verifier: verify candidate plus original_image
        Verifier->>Crop: build_verify_crops
        Crop-->>Verifier: original crop plus outlined candidate
        Verifier->>Gemini: two PNGs plus params JSON
        alt fail and retries left
            Note over Verifier: JSON includes SD fixes plus mask/compose dilate
            alt mask_dilate_pixels greater than 0
                Hybrid->>Lama: re-fill expanded hole
            end
            Hybrid->>SD: replay params from JSON
        end
    end
    Hybrid->>Hybrid: sharpen and color nudge
    Hybrid-->>BG: inpaint_out compose metadata
    BG->>BG: paste with widened compose mask
```

Default: compute one padded window from the mask (Gemini pad ratio 0.35, minimum side at least 256 px or 25% of the shorter image edge). Send **original crop** and **outlined candidate crop** plus current params to Gemini. Pass copies input knobs and sets dilate fields to `0`. Fail returns rewritten knobs plus AI-decided `mask_dilate_pixels` / `compose_dilate_pixels`. Placeholder `GEMINI_API_KEY` (or HTTP/JSON failure) uses CLIP labels instead (clean texture vs leftover shadow) with fixed dilate heuristics. On fail with mask dilation, Hybrid re-runs LaMa before SD. Exhausted retries keep the last candidate and log `verification_ok=False`.

Each Gemini attempt emits a structured INFO log (crop size, window, mask pixels, dual-crop flag, retry recipe on fail).
