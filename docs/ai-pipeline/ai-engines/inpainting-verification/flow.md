# Inpainting verification flow

```mermaid
sequenceDiagram
    participant BG as BackgroundInpainter
    participant Hybrid as HybridInpaintingStrategy
    participant Lama as LamaStrategy
    participant SD as StableDiffusionStrategy
    participant Verifier as InpaintingVerificationFacade

    BG->>Hybrid: inpaint refined_mask
    Hybrid->>Lama: structural fill
    alt strength greater than skip threshold
        Hybrid->>SD: first SD pass
    end
    loop until ok or retries exhausted
        Hybrid->>Verifier: verify padded crop
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

Default: pad-crop the mask (Gemini uses 0.35 pad ratio), send crop + current params to Gemini. Pass copies input knobs and sets dilate fields to `0`. Fail returns rewritten knobs plus AI-decided `mask_dilate_pixels` / `compose_dilate_pixels`. Placeholder `GEMINI_API_KEY` (or HTTP/JSON failure) uses CLIP labels instead (clean texture vs leftover shadow) with fixed dilate heuristics. On fail with mask dilation, Hybrid re-runs LaMa before SD. Exhausted retries keep the last candidate and log `verification_ok=False`.
