# AI Pipeline Docs

The AI pipeline is the Python package `avroom_object_removal`, with sources in [`TestModules/src/`](../../TestModules/src/). It does the actual depth → segmentation → inpainting work; the FastAPI backend is just a thin wrapper around it.

## Public surface

```1:3:TestModules/src/__init__.py
from .core.objectRemover import ObjectRemover

__all__ = ["ObjectRemover"]
```

One class, one method that matters: `ObjectRemover.remove_object(image_path, x, y, image_bytes=None)`.

## Pages

- [overview.md](overview.md) — package layout, install, public surface.
- [object-remover.md](object-remover.md) — the orchestrator and the 8 pipeline stages.
- [depth.md](depth.md) — the two-model alpha-blended depth facade.
- [segmentation.md](segmentation.md) — SAM facade and the depth-to-RGB adapter.
- [routing.md](routing.md) — the strategy that picks SAM input + expansion + SD strength.
- [inpainting.md](inpainting.md) — LaMa, Stable Diffusion, and the hybrid composition.
- [utils.md](utils.md) — `MaskRefiner`, `MaskOverlapRGBAComposer`, `DebugImageSaver`, `ImageAdapterFactory`.
- [tests.md](tests.md) — the integration scripts under `TestModules/tests/`.
- [outputs.md](outputs.md) — every debug PNG produced per call.
- [3d-reconstruction-hunyuan.md](3d-reconstruction-hunyuan.md) — Hunyuan3D-2.1 stub; not wired in.
- [data-flow.md](data-flow.md) — line-by-line trace through `remove_object`.

## At a glance

```mermaid
flowchart LR
    input(["image + (x, y)"])
    depth["OptimizedDepthFacade<br/>(2x DepthAnything alpha-blend)"]
    adapter["SamImageAdapter<br/>(depth -> 3-channel RGB, cached)"]
    router["BoundaryVarianceRoutingStrategy<br/>(decides expand_pixels, sd_strength)"]
    sam["SamFacadeSingleton<br/>(SAM ViT-B, masks[1])"]
    refine["MaskRefiner.expand_mask_uniform<br/>(radius=3, downward bias)"]
    hybrid["HybridInpainter<br/>(LaMa -> optional SD)"]
    compose["MaskOverlapRGBAComposer<br/>(BGRA cutout)"]
    out(["background_bgr, cutout_bgra"])

    input --> depth --> adapter --> router --> sam --> refine --> hybrid --> out
    input --> hybrid
    input --> compose --> out
    refine --> compose
```
