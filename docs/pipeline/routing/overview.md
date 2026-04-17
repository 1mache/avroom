# Routing Overview

## Purpose

The routing layer answers one question before SAM runs:

> Given the scene geometry around the clicked point, what is the best configuration for the segmentation and inpainting steps?

Routing sits between depth estimation and SAM. It receives the click coordinates, the depth map, the adapted depth map, and the original RGB image, then returns a `run_context` dict that configures the rest of the pipeline.

## The `ISegmentationRoutingStrategy` Contract

```python
def choose_input(
    self,
    rgb_image: np.ndarray,
    raw_depth: np.ndarray,
    adapted_depth: np.ndarray,
    x: int,
    y: int,
) -> dict[str, Any]
```

All strategies must return a dict with these keys:

| Key | Type | Effect |
|---|---|---|
| `input_image` | `np.ndarray` | Image passed to SAM — either adapted depth or raw RGB |
| `sd_strength` | `float` | SD inpainting strength in `HybridInpainter` |
| `use_broad_mask` | `bool` | Whether to prefer the broader SAM mask candidate |
| `expand_pixels` | `int` | Dilation applied inside `SamFacadeSingleton.get_mask_at_point` |

See [`core/interfaces.md`](../core/interfaces.md#isegmentationroutingstrategy).

## Active Strategy

`ObjectRemover` currently wires **`BoundaryVarianceRoutingStrategy`**:

```python
self.router = BoundaryVarianceRoutingStrategy(sam_facade=self.sam)
```

All other strategies are available in `TestModules/src/routing/` and can be substituted without any changes to `ObjectRemover`.

## Strategy Summary

| Strategy | Classification Signal | Active? |
|---|---|---|
| `BoundaryVarianceRoutingStrategy` | Depth variance on a ring around the SAM probe mask | **Yes** |
| `GradientVarianceRoutingStrategy` | Sobel gradient variance in a local depth window | No |
| `VarianceBasedRoutingStrategy` | Raw depth variance in a local window | No |
| `CenterOfMassRoutingStrategy` | Median depth difference: object vs local background | No |
| `TopographicRoutingStrategy` | Local depth range + protrusion above background | No |

## Core Decision: 3D Object vs Flat Surface

Every strategy classifies the clicked object into one of two categories and adjusts the `run_context` accordingly:

| Class | Example Objects | Typical Effect |
|---|---|---|
| **3D Object** | Sofa, pouf, table, armchair | Larger `expand_pixels`, adapted depth as SAM input |
| **Flat Surface** | TV, picture frame, window, wall art | Smaller `expand_pixels`, tighter mask |

## Individual Strategy Docs

- [`boundary-variance-strategy.md`](boundary-variance-strategy.md) — active strategy (recommended)
- [`gradient-variance-strategy.md`](gradient-variance-strategy.md) — Sobel-based alternative
- [`other-strategies.md`](other-strategies.md) — variance-based, center-of-mass, topographic
