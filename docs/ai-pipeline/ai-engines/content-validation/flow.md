# Content validation flow

## Upload gate (end-to-end)

```mermaid
sequenceDiagram
    participant Client
    participant Router as api_routes
    participant Tech as ImageValidator
    participant Pool as InferenceClient
    participant Core as ContentImageValidator
    participant Facade as ContentValidationFacade

    Client->>Router: POST /images/upload
    Router->>Tech: validate(bytes)
    alt technical fail
        Router-->>Client: 422
    end
    Router->>Pool: run_validate_content(bytes)
    Pool->>Core: validate_upload(memory key, bytes)
    Core->>Facade: validate(bgr)
    Facade-->>Core: ContentValidationResult
    Core-->>Pool: outcome
    alt content fail
        Router-->>Client: 422
    end
    Router->>Router: write_bytes + register_uid
    Router-->>Client: ImageUploadResponse
```

## CLIP strategy steps

1. Convert BGR input to RGB PIL image.
2. Score label groups via CLIP (`openai/clip-vit-base-patch32`, lazy-loaded).
3. Derive seven named checks (see [contracts.md](contracts.md)).
4. Aggregate pass/fail and human-readable rejection messages.

## Composite strategy

Runs each child strategy in order, merges `checks`/`scores`/`messages`, sets `is_valid = all(checks.values())`.
