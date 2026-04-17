# Pipeline Overview

## What Is the Pipeline?

The pipeline is the core CV/ML system that takes a room image and a click coordinate, segments the object under the click, and returns a background with the object removed plus a transparent cutout of the removed object.

All pipeline code lives in `TestModules/src/`.

## Entry Point

`ObjectRemover.remove_object(image_path, x, y)` in [`TestModules/src/core/objectRemover.py`](../../TestModules/src/core/objectRemover.py) is the single entry point called by the API layer.

## Pipeline Stages

| Stage | Class | File |
|---|---|---|
| 1. Depth estimation | `OptimizedDepthFacade` | `ai_engines/depth/OptimizedDepthFacade.py` |
| 2. Depth adaptation | `SamImageAdapter` | `ai_engines/segmentation/SamImageAdapter.py` |
| 3. Routing decision | `BoundaryVarianceRoutingStrategy` | `routing/boundary_variance_strategy.py` |
| 4. Segmentation | `SamFacadeSingleton` | `ai_engines/segmentation/SamFacadeSingleton.py` |
| 5. Mask refinement | `MaskRefiner` | `utils/MaskRefiner.py` |
| 6. Inpainting | `HybridInpainter` | `ai_engines/inpainting/HybridInpainter.py` |
| 7. Cutout composition | `MaskOverlapRGBAComposer` | `utils/MaskOverlapRGBAComposer.py` |

## Subsystem Documentation

- [`core/object-remover.md`](core/object-remover.md) — orchestrator logic, step-by-step
- [`core/interfaces.md`](core/interfaces.md) — abstract contracts for all components
- [`ai-engines/depth/`](ai-engines/depth/depth-mapper.md) — depth estimation models
- [`ai-engines/segmentation/`](ai-engines/segmentation/sam-facade.md) — SAM and depth adapter
- [`ai-engines/inpainting/`](ai-engines/inpainting/hybrid-inpainter.md) — LaMa and Stable Diffusion
- [`routing/`](routing/overview.md) — strategy pattern for SAM input selection
- [`utils/`](utils/mask-refiner.md) — shared utilities

## Package Layout and Import Paths

When imported from within `TestModules/src/` (or via the API sys.path patch), the top-level package names are:

```
core.*          →  TestModules/src/core/
ai_engines.*    →  TestModules/src/ai_engines/
routing.*       →  TestModules/src/routing/
utils.*         →  TestModules/src/utils/
```

The `fastApi-app` service patches `sys.modules` before importing `ObjectRemover` to prevent name collisions with its own `core` package. See [`docs/api/image-processing.md`](../../api/image-processing.md).

## Runtime Directories

| Path | Purpose |
|---|---|
| `TestModules/checkpoints/` | SAM model weights (gitignored) |
| `TestModules/inputs/` | Test images for `GuiTestClicker` (gitignored) |
| `TestModules/outputs/` | Debug intermediate images from `DebugImageSaver` (gitignored) |
