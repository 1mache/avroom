# Novel view execution and data flow

Invoked via `NovelViewFacade.synthesize(...)` or `POST /images/novel-view`.

## Stable Zero123 (default)

1. Resolve cutout path on disk (`{uid}_{object_id}_cutout.png`).
2. Normalize to PIL RGBA (`to_pil_rgba`).
3. Crop to alpha bounding box; pad to square; resize to 256×256.
4. Lazy-load Diffusers Zero1to3 pipeline on `kxic/stable-zero123` (override via `NOVEL_VIEW_MODEL_ID`).
5. Run inference with pose `[elevation_deg + relative_elevation_deg, azimuth_deg, radius]`, `guidance_scale≈3`.
6. Remask generated RGB (white background → transparent alpha).
7. Upscale and composite back onto full-size transparent canvas.
8. Encode PNG → base64; compute `cutout_bounds`; optionally persist disk cache.

```mermaid
sequenceDiagram
  participant API
  participant Facade as NovelViewFacade
  participant Strategy as StableZero123
  participant Model as Zero123Pipeline

  API->>Facade: synthesize(cutout_path, pose)
  Facade->>Strategy: synthesize(...)
  Strategy->>Strategy: crop pad resize 256
  Strategy->>Model: input_imgs + poses
  Model-->>Strategy: RGB PIL
  Strategy->>Strategy: remask composite canvas
  Strategy-->>Facade: BGRA ndarray
  Facade-->>API: BGRA ndarray
```

## Pose semantics

The Zero1to3 community pipeline encodes pose as `[elevation, azimuth, radius]`:

- **elevation** — target view elevation in degrees (source absolute + relative delta)
- **azimuth** — relative rotation from source to target
- **radius** — camera distance / zoom (0 = default)

Use **low CFG (~3)**; higher values over-amplify pose conditioning.

## Known limits

- Large azimuth angles hallucinate unseen object backsides.
- Pose is not guaranteed geometrically identical to a Trellis GLB orbit view.
- Model is object-centric (Objaverse-style); cutout must be centered and isolated.
