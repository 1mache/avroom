# Reconstruction 3D execution and data flow

Not invoked inside `ObjectRemover.remove_object`. Invoked instead from `POST /3d/test-3d` and `POST /images/novel-view` via `core/inference_pool`'s `JobKind.GENERATE_3D` dispatch, which constructs a bare `Reconstruction3DFacade()` (no explicit strategy) at `quality=ReconstructionQuality.HIGH`.

## Facade dispatch (every call)

1. `Reconstruction3DFacade.generate(...)` calls the primary strategy (`Hunyuan3D2ReconstructionStrategy` by default).
2. If the primary raises, the facade logs a warning and retries with the fallback strategy (`TriposrReconstructionStrategy`), same arguments.
3. If the fallback also raises, the facade raises one `RuntimeError` wrapping both original exceptions.

## Hunyuan3D-2.1 (default)

Used when the facade is constructed with no strategy, or with `Hunyuan3D2ReconstructionStrategy()` explicitly.

1. Normalize arbitrary image input to PIL RGBA (`to_pil_rgba`).
2. Clean the cutout: zero out near-transparent alpha ("shadow dust") below a threshold, then crop to the visible bounding box and re-center it on a padded transparent square canvas — both steps prevent the model from generating a warped floor/blob under the object.
3. Save the cleaned image to a temp PNG and connect (lazily, cached on the strategy instance) a `gradio_client.Client` to the Space.
4. Call `/generation_all` (shape + texture → textured GLB). If that call raises or returns no GLB path, fall back to `/shape_generation` (shape only → untextured GLB).
5. If both endpoint calls fail, raise `Hunyuan3D2GenerationError`.
6. Return payload according to `output` mode (`bytes`, `path`, file-like) via `write_output`.

Space id, quality-preset mapping, and errors: [operations.md](operations.md).

## TripoSR (automatic fallback)

Used automatically when the primary strategy raises, or explicitly via `TriposrReconstructionStrategy()`.

1. Normalize arbitrary image input to PIL RGBA (`to_pil_rgba`).
2. Preprocess RGBA → RGB composited over neutral background (matching upstream TripoSR defaults).
3. Lazy-load `TSR.from_pretrained("stabilityai/TripoSR")` and run inference on CUDA if available (fallback CPU).
4. Extract a mesh (marching cubes resolution depends on `ReconstructionQuality`) and export as GLB.
5. Return according to `output` mode (`bytes`, `path`, file-like).

## OpenLRM (optional, explicit injection only)

1. Normalize arbitrary image input to PIL RGBA (`to_pil_rgba`).
2. Write a temporary PNG under a private work directory.
3. Run vendored `LRMInferrer` (lazy-loaded once per process) to produce a mesh (intermediate PLY in the work dir).
4. Convert mesh to GLB (`trimesh`) and package via `write_output` according to `output` (`bytes`, `path`, file-like).

Cache, env vars, and pip deps: [operations.md](operations.md).

## Trellis (optional, explicit injection only, unused by default and by the fallback path)

Used only when the facade is constructed with `TrellisReconstructionStrategy()` explicitly.

1. Normalize arbitrary image input to PIL RGBA.
2. Map `ReconstructionQuality` preset to Space parameters (resolution, steps, mesh decimation, texture resolution) via the shared `GenerationParams`/`PRESETS` table.
3. Submit the Space job, poll/fetch the GLB result.
4. Return payload according to `output` mode (`bytes`, `path`, file-like).

Space id and errors: [operations.md](operations.md).
