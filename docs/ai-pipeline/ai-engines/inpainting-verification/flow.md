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

CLIP v1: pad-crop the mask, score labels, pass if `photorealistic room` wins. On fail, JSON is the params that were used (no invented knobs). Exhausted retries keep the last candidate.
