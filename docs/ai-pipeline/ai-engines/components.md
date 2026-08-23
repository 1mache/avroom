# AI Engines components

Pattern everywhere under [`TestModules/src/ai_engines/`](../../../TestModules/src/ai_engines/): **Facade + Strategy**.

## Domain facades (stable imports)

| Domain | Facade | Default strategy focus |
|--------|--------|-------------------------|
| Depth | `DepthMappingFacade` | Near/far blend (`NearFarBlendedDepthMappingStrategy`) |
| Segmentation | `ImageSegmentationFacade` | SAM (`SamSegmentationStrategy`) |
| Inpainting | `ImageInpaintingFacade` | LaMa + optional SD (`HybridInpaintingStrategy`) |
| Novel view | `NovelViewFacade` | Facade default: Stable Zero123; HTTP: MeshRender (`MeshRenderNovelViewStrategy`) |
| Reconstruction 3D | `Reconstruction3DFacade` | Hunyuan3D-2.1 HF Space (`Hunyuan3D2ReconstructionStrategy`, default), automatic fallback to TripoSR (`TriposrReconstructionStrategy`); OpenLRM/Trellis/VFusion3D when injected |
| Content validation | `ContentValidationFacade` | CLIP zero-shot (`ClipZeroShotContentValidationStrategy` via composite) |
| Inpainting verification | `InpaintingVerificationFacade` | CLIP labels on padded crop (`ClipLabelInpaintingVerificationStrategy`) |
| Normal mapping | `NormalMappingFacade` | Metric3D ViT (`Metric3DNormalMappingStrategy`; debug only) |

Each facade holds one active `*Strategy` instance configured at construction.

## Abstract interfaces

- `DepthMappingStrategy`
- `ImageSegmentationStrategy`
- `ImageInpaintingStrategy`
- `NovelViewStrategy`
- `Reconstruction3DStrategy`
- `ContentValidationStrategy`
- `InpaintingVerificationStrategy`
- `NormalMappingStrategy`

Concrete implementations live under each domain’s `strategies/` package.

## Shared helpers

Engines rely on [`utils/`](../utils/README.md) (`DebugImageSaver`, `MaskRefiner`, `colorize_normals` where relevant) rather than duplicating I/O.

## Per-domain docs

- [depth/README.md](depth/README.md)
- [segmentation/README.md](segmentation/README.md)
- [inpainting/README.md](inpainting/README.md)
- [novel-view/README.md](novel-view/README.md)
- [reconstruction-3d/README.md](reconstruction-3d/README.md)
- [content-validation/README.md](content-validation/README.md)
- [inpainting-verification/README.md](inpainting-verification/README.md)
- [normal-mapping/README.md](normal-mapping/README.md)
