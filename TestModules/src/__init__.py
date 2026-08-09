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
    CameraCalibrationFacade,
    CameraCalibrationResult,
    CameraCalibrationStrategy,
    ClipZeroShotContentValidationStrategy,
    CompositeContentValidationStrategy,
    ContentValidationFacade,
    ContentValidationResult,
    ContentValidationStrategy,
    DepthAnythingMappingStrategy,
    DepthMappingFacade,
    DepthMappingStrategy,
    ElevationEstimationFacade,
    ElevationEstimationResult,
    ElevationEstimationStrategy,
    GeometricElevationEstimationStrategy,
    GeoCalibCameraCalibrationStrategy,
    HybridInpaintingStrategy,
    ImageInpaintingFacade,
    ImageInpaintingStrategy,
    ImageSegmentationFacade,
    ImageSegmentationStrategy,
    LamaInpaintingStrategy,
    NearFarBlendedDepthMappingStrategy,
    NovelViewFacade,
    NovelViewStrategy,
    OpenLrmReconstructionStrategy,
    Reconstruction3DFacade,
    Reconstruction3DStrategy,
    ReconstructionQuality,
    SamImageAdapter,
    SamSegmentationStrategy,
    StableDiffusionInpaintingStrategy,
    StableZero123NovelViewError,
    StableZero123NovelViewStrategy,
    TrellisReconstructionStrategy,
)
from .core import (
    BackgroundInpainter,
    ContentImageValidator,
    CutoutSelectionResult,
    ObjectRemover,
    ObjectSegmentor,
    select_best_cutout,
)
from .routing import (
    BoundaryVarianceRoutingStrategy,
    CenterOfMassRoutingStrategy,
    SegmentationRoutingStrategy,
)

__all__ = [
    "BoundaryVarianceRoutingStrategy",
    "CenterOfMassRoutingStrategy",
    "CameraCalibrationFacade",
    "CameraCalibrationResult",
    "CameraCalibrationStrategy",
    "ClipZeroShotContentValidationStrategy",
    "CompositeContentValidationStrategy",
    "ContentImageValidator",
    "CutoutSelectionResult",
    "ContentValidationFacade",
    "ContentValidationResult",
    "ContentValidationStrategy",
    "DepthAnythingMappingStrategy",
    "DepthMappingFacade",
    "DepthMappingStrategy",
    "ElevationEstimationFacade",
    "ElevationEstimationResult",
    "ElevationEstimationStrategy",
    "GeometricElevationEstimationStrategy",
    "GeoCalibCameraCalibrationStrategy",
    "HybridInpaintingStrategy",
    "ImageInpaintingFacade",
    "ImageInpaintingStrategy",
    "ImageSegmentationFacade",
    "ImageSegmentationStrategy",
    "LamaInpaintingStrategy",
    "NearFarBlendedDepthMappingStrategy",
    "NovelViewFacade",
    "NovelViewStrategy",
    "BackgroundInpainter",
    "ObjectRemover",
    "ObjectSegmentor",
    "OpenLrmReconstructionStrategy",
    "Reconstruction3DFacade",
    "Reconstruction3DStrategy",
    "ReconstructionQuality",
    "SamImageAdapter",
    "select_best_cutout",
    "SamSegmentationStrategy",
    "SegmentationRoutingStrategy",
    "StableDiffusionInpaintingStrategy",
    "StableZero123NovelViewError",
    "StableZero123NovelViewStrategy",
    "TrellisReconstructionStrategy",
]
