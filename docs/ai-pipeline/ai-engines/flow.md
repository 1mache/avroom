# AI Engines execution pattern

Every domain facade follows the same call shape:

1. Core passes normalized arrays (BGR image, masks, etc.).
2. Facade validates or reshapes minimally, then forwards to its strategy.
3. Strategy loads or reuses cached model handles (`functools.lru_cache` at module scope).
4. Strategy runs inference and post-processing.
5. Output dtypes/shapes match what the **next pipeline stage** expects (`ObjectRemover` order is fixed).

Depth runs first in the removal pipeline; segmentation and inpainting consume its outputs indirectly (adapted depth, masks). Reconstruction 3D is **outside** `remove_object`; tests call it separately.
