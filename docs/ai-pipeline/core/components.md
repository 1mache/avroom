# Core components

Source: [`TestModules/src/core/`](../../../TestModules/src/core/).

## Orchestrator

- **`ObjectRemover`** — Master facade for `remove_object`. Owns stage order and wires collaborators via constructor injection.

## Helpers inside core

- **`_ensure_mask_hw`** — Aligns mask height/width with the image and normalizes mask value semantics before pixel indexing and composition.

## Wiring

Constructor dependency injection supplies defaults for:

- `DepthMappingFacade`, `ImageSegmentationFacade`, `ImageInpaintingFacade`
- `SegmentationRoutingStrategy` (default `BoundaryVarianceRoutingStrategy`)
- `SamImageAdapter`, `MaskRefiner`, `BgraCutoutComposer`, `DebugImageSaver`

## Coupling

- **Upstream callers:** [`fastApi-app/core/image_processing.py`](../../../fastApi-app/core/image_processing.py) (`segment_at_click`), manual scripts under [`TestModules/tests/`](../../../TestModules/tests/).
- **Downstream:** all pipeline domains listed on [README](README.md).
