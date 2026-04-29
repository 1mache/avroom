# AI Pipeline Overview

## Distribution

The package is declared in [`TestModules/pyproject.toml`](../../TestModules/pyproject.toml):

```1:24:TestModules/pyproject.toml
[build-system]
requires = ["setuptools>=65"]
build-backend = "setuptools.build_meta"

[project]
name = "avroom-object-removal"
version = "0.1.0"
description = "Object removal pipeline extracted from TestModules."
requires-python = ">=3.11"

[tool.setuptools]
packages = [
    "avroom_object_removal",
    "avroom_object_removal.ai_engines",
    "avroom_object_removal.ai_engines.depth",
    "avroom_object_removal.ai_engines.inpainting",
    "avroom_object_removal.ai_engines.segmentation",
    "avroom_object_removal.core",
    "avroom_object_removal.routing",
    "avroom_object_removal.utils",
]

[tool.setuptools.package-dir]
avroom_object_removal = "src"
```

Notice the source-to-import remap: code lives at `TestModules/src/...` but is imported as `avroom_object_removal.*`.

There is **no** `[project.dependencies]` block; runtime deps are pinned in the root [`requirements.txt`](../../requirements.txt). The first line of that file installs this package editable:

```1:1:requirements.txt
-e ./TestModules
```

## Public API

```1:3:TestModules/src/__init__.py
from .core.objectRemover import ObjectRemover

__all__ = ["ObjectRemover"]
```

The only thing meant to be used from outside is `ObjectRemover.remove_object(...)`. All facades, singletons, adapters, and strategies are internal to this package.

## Internal package layout

```
avroom_object_removal/  (= TestModules/src/)
├── __init__.py
├── GuiTestClicker.py             - manual GUI test harness
├── core/
│   ├── __init__.py
│   ├── interfaces.py             - IDepthFacade, IImageAdapter, IInpainter, ISegmentationRoutingStrategy
│   └── objectRemover.py          - ObjectRemover (the orchestrator)
├── ai_engines/
│   ├── __init__.py
│   ├── depth/
│   │   ├── __init__.py
│   │   ├── ImageDepthMapper.py
│   │   └── OptimizedDepthFacade.py
│   ├── inpainting/
│   │   ├── __init__.py
│   │   ├── LamaInpainter.py
│   │   ├── StableDiffusionInpainter.py
│   │   └── HybridInpainter.py
│   ├── segmentation/
│   │   ├── __init__.py
│   │   ├── SamFacadeSingleton.py
│   │   └── SamImageAdapter.py
│   └── 3dRreconstruction/
│       └── Hunyuan3D-2.1/        - upstream checkout, NOT wired in
├── routing/
│   ├── __init__.py
│   ├── boundary_variance_strategy.py    - the only one used in production
│   ├── variance_based_routing_strategy.py
│   ├── gradient_variance_routing_strategy.py
│   ├── topographic_routing_strategy.py
│   └── center_of_mass_routing_strategy.py
└── utils/
    ├── __init__.py
    ├── DebugImageSaver.py
    ├── ImageAdapterFactory.py    (file: imageAdapterFactory.py)
    ├── MaskRefiner.py
    └── MaskOverlapRGBAComposer.py
```

## Required runtime resources

| Resource | Where it goes | How it's resolved |
|---|---|---|
| SAM ViT-B checkpoint (`sam_vit_b_01ec64.pth`) | `TestModules/checkpoints/` | `SAM_CHECKPOINT_PATH` env, then default path, then auto-download. See [`SamFacadeSingleton.py`](../../TestModules/src/ai_engines/segmentation/SamFacadeSingleton.py) lines 20–55. |
| Depth-Anything HF models | HF cache (default `~/.cache/huggingface/`) | `transformers.pipeline(model=...)` downloads on first call. |
| LaMa weights | bundled with `simple_lama_inpainting` | Loaded by `SimpleLama()` inside [`LamaInpainter`](../../TestModules/src/ai_engines/inpainting/LamaInpainter.py). |
| `runwayml/stable-diffusion-inpainting` | HF cache | `StableDiffusionInpaintPipeline.from_pretrained(...)` on first call. |

## Where to read next

- The orchestrator: [object-remover.md](object-remover.md).
- A line-by-line walk: [data-flow.md](data-flow.md).
- The patterns it leans on: [../conventions.md](../conventions.md).
