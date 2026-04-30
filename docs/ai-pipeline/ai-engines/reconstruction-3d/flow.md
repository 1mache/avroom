# Reconstruction 3D execution and data flow

Not invoked inside `ObjectRemover.remove_object`.

## OpenLRM (default)

Used when `Reconstruction3DFacade()` is constructed with no strategy (or `OpenLrmReconstructionStrategy` explicitly).

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
