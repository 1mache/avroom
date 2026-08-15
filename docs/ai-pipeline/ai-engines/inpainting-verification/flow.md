# Inpainting verification flow

```mermaid
sequenceDiagram
    participant Hybrid as HybridInpaintingStrategy
    participant Lama as LamaStrategy
    participant SD as StableDiffusionStrategy
    participant Verifier as InpaintingVerificationFacade

    Hybrid->>Lama: inpaint once
    alt strength greater than skip threshold
        Hybrid->>SD: first SD pass
    end
    loop until ok or retries exhausted
        Hybrid->>Verifier: verify candidate crop
        alt fail and retries left
            Hybrid->>SD: replay params from JSON
        end
    end
    Hybrid->>Hybrid: sharpen and color nudge
```

Default: pad-crop the mask, send crop + current params to Gemini. Pass copies input knobs. Fail returns rewritten knobs. Placeholder `GEMINI_API_KEY` (or HTTP/JSON failure) uses CLIP labels instead (`photorealistic room` wins). Exhausted retries keep the last candidate.
