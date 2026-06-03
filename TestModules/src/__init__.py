"""Public API of the ``avroom_object_removal`` package.

Re-exports the master :class:`ObjectRemover` Facade plus the four per-domain
Facades and their Strategy ABCs so client code can write::

    from avroom_object_removal import ObjectRemover
    from avroom_object_removal import (
        DepthMappingFacade,
        ImageSegmentationFacade,
        ImageInpaintingFacade,
        Reconstruction3DFacade,
    )

without ever importing from internal sub-paths.
"""

from __future__ import annotations

from .ai_engines import (
    DepthAnythingMappingStrategy,
    DepthMappingFacade,
    DepthMappingStrategy,
    HybridInpaintingStrategy,
    ImageInpaintingFacade,
    ImageInpaintingStrategy,
    ImageSegmentationFacade,
    ImageSegmentationStrategy,
    LamaInpaintingStrategy,
    NearFarBlendedDepthMappingStrategy,
    OpenLrmReconstructionStrategy,
    Reconstruction3DFacade,
    Reconstruction3DStrategy,
    ReconstructionQuality,
    SamImageAdapter,
    SamSegmentationStrategy,
    StableDiffusionInpaintingStrategy,
    TrellisReconstructionStrategy,
)
from .core import BackgroundInpainter, ObjectRemover, ObjectSegmentor
from .routing import (
    BoundaryVarianceRoutingStrategy,
    CenterOfMassRoutingStrategy,
    SegmentationRoutingStrategy,
)

__all__ = [
    "BoundaryVarianceRoutingStrategy",
    "CenterOfMassRoutingStrategy",
    "DepthAnythingMappingStrategy",
    "DepthMappingFacade",
    "DepthMappingStrategy",
    "HybridInpaintingStrategy",
    "ImageInpaintingFacade",
    "ImageInpaintingStrategy",
    "ImageSegmentationFacade",
    "ImageSegmentationStrategy",
    "LamaInpaintingStrategy",
    "NearFarBlendedDepthMappingStrategy",
    "BackgroundInpainter",
    "ObjectRemover",
    "ObjectSegmentor",
    "OpenLrmReconstructionStrategy",
    "Reconstruction3DFacade",
    "Reconstruction3DStrategy",
    "ReconstructionQuality",
    "SamImageAdapter",
    "SamSegmentationStrategy",
    "SegmentationRoutingStrategy",
    "StableDiffusionInpaintingStrategy",
    "TrellisReconstructionStrategy",
]
