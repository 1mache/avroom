# Reconstruction 3D execution and data flow

Not invoked inside `ObjectRemover.remove_object`.

## OpenLRM (optional)

OpenLRM is used when the facade is constructed with `OpenLrmReconstructionStrategy()` explicitly.

1. Normalize arbitrary image input to PIL RGBA (`to_pil_rgba`).
2. Write a temporary PNG under a private work directory.
3. Run vendored `LRMInferrer` (lazy-loaded once per process) to produce a mesh (intermediate PLY in the work dir).
4. Convert mesh to GLB (`trimesh`) and package via `write_output` according to `output` (`bytes`, `path`, file-like).

Cache, env vars, and pip deps: [operations.md](operations.md).

## Trellis (optional)

Used when the facade is constructed with `TrellisReconstructionStrategy()` (or any custom strategy that implements the Space flow).

1. Normalize arbitrary image input to PIL RGBA.
2. Map `ReconstructionQuality` preset to Space parameters (resolution, steps, mesh decimation, texture resolution).
3. Submit `/image_to_3d` job.
4. Poll/fetch `/extract_glb` result.
5. Return payload according to `output` mode (`bytes`, `path`, file-like).

Space id, auth, and errors: [operations.md](operations.md).

## TripoSR (default)

Used when `Reconstruction3DFacade()` is constructed with no strategy (or `TriposrReconstructionStrategy` explicitly).

1. Normalize arbitrary image input to PIL RGBA (`to_pil_rgba`).
2. Preprocess RGBA → RGB composited over neutral background (matching upstream TripoSR defaults).
3. Lazy-load `TSR.from_pretrained("stabilityai/TripoSR")` and run inference on CUDA if available (fallback CPU).
4. Extract a mesh (marching cubes resolution depends on `ReconstructionQuality`) and export as GLB.
5. Return according to `output` mode (`bytes`, `path`, file-like).
