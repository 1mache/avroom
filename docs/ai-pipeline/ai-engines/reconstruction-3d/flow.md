# Reconstruction 3D execution and data flow

1. Normalize arbitrary image input to PIL RGBA.
2. Map `ReconstructionQuality` preset to Space parameters (resolution, steps, mesh decimation, texture resolution).
3. Submit `/image_to_3d` job.
4. Poll/fetch `/extract_glb` result.
5. Return payload according to `output` mode (`bytes`, `path`, file-like).

Not invoked inside `ObjectRemover.remove_object`.
