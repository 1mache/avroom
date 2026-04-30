# AI Engines components

Pattern everywhere under [`TestModules/src/ai_engines/`](../../../TestModules/src/ai_engines/): **Facade + Strategy**.

## Domain facades (stable imports)

| Domain | Facade | Default strategy focus |
|--------|--------|-------------------------|
| Depth | `DepthMappingFacade` | Near/far blend (`NearFarBlendedDepthMappingStrategy`) |
| Segmentation | `ImageSegmentationFacade` | SAM (`SamSegmentationStrategy`) |
| Inpainting | `ImageInpaintingFacade` | LaMa + optional SD (`HybridInpaintingStrategy`) |
| Reconstruction 3D | `Reconstruction3DFacade` | OpenLRM local (`OpenLrmReconstructionStrategy`, default); Trellis HF Space (`TrellisReconstructionStrategy`) when injected |

Each facade holds one active `*Strategy` instance configured at construction.

## Abstract interfaces

- `DepthMappingStrategy`
- `ImageSegmentationStrategy`
- `ImageInpaintingStrategy`
- `Reconstruction3DStrategy`

Concrete implementations live under each domain’s `strategies/` package.

## Shared helpers

Engines rely on [`utils/`](../utils/README.md) (`DebugImageSaver`, `MaskRefiner` where relevant) rather than duplicating I/O.

## Per-domain docs

- [depth/README.md](depth/README.md)
- [segmentation/README.md](segmentation/README.md)
- [inpainting/README.md](inpainting/README.md)
- [reconstruction-3d/README.md](reconstruction-3d/README.md)
