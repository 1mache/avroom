# Routing components

Source: [`TestModules/src/routing/`](../../../TestModules/src/routing/).

- **`SegmentationRoutingStrategy`** — ABC with `choose_input(rgb_image, raw_depth, adapted_depth, x, y) -> dict`.
- **`BoundaryVarianceRoutingStrategy`** — Default used by `ObjectRemover`: probes SAM mask with zero dilation, measures depth variance along boundary ring, derives expand pixels + strength choices.
- **`CenterOfMassRoutingStrategy`** — Alternate/experimental router retained in repo.

Router receives the **same** `ImageSegmentationFacade` instance as core so probe and final segmentation share predictor caches.
