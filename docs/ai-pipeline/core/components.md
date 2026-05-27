# Core components

Source: [`TestModules/src/core/`](../../../TestModules/src/core/).

## Orchestrators

- **`ObjectRemover`** — Master facade for `remove_object`. Owns all 7 stage order and wires collaborators via constructor injection.
- **`ObjectSegmentor`** — Segmentation-only facade for `get_mask_for_object_at_position`. Runs stages 1–3 and 5–7 (omits inpainting). Returns all SAM candidates as `(refined_mask, cutout_bgra)` pairs.
- **`BackgroundInpainter`** — Inpainting-only facade for `cut_mask_from_image`. Runs stage 4 only. Accepts a BGR image and a mask; returns the inpainted BGR scene.

## Shared helpers

- **`ensure_mask_hw`** (module `_mask_utils.py`) — Aligns mask height/width with the image and normalises mask value semantics before pixel indexing and composition. Shared by `ObjectRemover` and `ObjectSegmentor`.

## Wiring

Constructor dependency injection supplies defaults for each orchestrator:

| Collaborator | ObjectRemover | ObjectSegmentor | BackgroundInpainter |
|---|---|---|---|
| `DepthMappingFacade` | ✓ | ✓ | — |
| `ImageSegmentationFacade` | ✓ | ✓ | — |
| `ImageInpaintingFacade` | ✓ | — | ✓ |
| `SegmentationRoutingStrategy` | ✓ (default `BoundaryVarianceRoutingStrategy`) | ✓ | — |
| `SamImageAdapter` | ✓ | ✓ | — |
| `MaskRefiner` | ✓ | ✓ | — |
| `DebugImageSaver` | ✓ | ✓ | ✓ |

## Coupling

- **Upstream callers:** [`fastApi-app/core/image_processing.py`](../../../fastApi-app/core/image_processing.py) (`segment_at_click` uses `ObjectRemover`), manual scripts under [`TestModules/tests/`](../../../TestModules/tests/).
- **Downstream:** all pipeline domains listed on [README](README.md).
