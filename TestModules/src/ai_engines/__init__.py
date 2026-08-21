from __future__ import annotations

from .camera_calibration import (
    CameraCalibrationFacade,
    CameraCalibrationResult,
    CameraCalibrationStrategy,
    GeoCalibCameraCalibrationStrategy,
)
from .content_validation import (
    ClipZeroShotContentValidationStrategy,
    CompositeContentValidationStrategy,
    ContentValidationFacade,
    ContentValidationResult,
    ContentValidationStrategy,
)
from .elevation_estimation import (
    ElevationEstimationFacade,
    ElevationEstimationResult,
    ElevationEstimationStrategy,
    GeometricElevationEstimationStrategy,
)
from .depth import (
    DepthAnythingMappingStrategy,
    DepthMappingFacade,
    DepthMappingStrategy,
    NearFarBlendedDepthMappingStrategy,
)
from .inpainting import (
    HybridInpaintingStrategy,
    ImageInpaintingFacade,
    ImageInpaintingStrategy,
    LamaInpaintingStrategy,
    StableDiffusionInpaintingStrategy,
)
from .inpainting_verification import (
    ClipLabelInpaintingVerificationStrategy,
    GeminiInpaintingVerificationStrategy,
    INPAINT_VERIFY_CROP_PAD_RATIO,
    InpaintSdParams,
    InpaintingVerificationFacade,
    InpaintingVerificationResult,
    InpaintingVerificationStrategy,
    crop_around_mask,
)
from .mask_selection import (
    AbsoluteClipGateStrategy,
    GeminiCutoutAllCandidatesTiebreakStrategy,
    GeminiCutoutTiebreakStrategy,
    MaskSelectionStrategy,
    MaskSelectionTiebreakStrategy,
    RelativeClipRankingStrategy,
)
from .normal_mapping import (
    Metric3DNormalMappingStrategy,
    NormalMappingFacade,
    NormalMappingStrategy,
)
from .novel_view import (
    NovelViewFacade,
    NovelViewStrategy,
    StableZero123NovelViewError,
    StableZero123NovelViewStrategy,
)
from .reconstruction_3d import (
    Hunyuan3D2GenerationError,
    Hunyuan3D2ReconstructionStrategy,
    OpenLrmReconstructionStrategy,
    Reconstruction3DFacade,
    Reconstruction3DStrategy,
    ReconstructionQuality,
    TrellisReconstructionStrategy,
)
from .segmentation import (
    ImageSegmentationFacade,
    ImageSegmentationStrategy,
    SamImageAdapter,
    SamSegmentationStrategy,
)

__all__ = [
    "CameraCalibrationFacade",
    "CameraCalibrationResult",
    "CameraCalibrationStrategy",
    "GeoCalibCameraCalibrationStrategy",
    "ClipZeroShotContentValidationStrategy",
    "CompositeContentValidationStrategy",
    "ContentValidationFacade",
    "ContentValidationResult",
    "ContentValidationStrategy",
    "ElevationEstimationFacade",
    "ElevationEstimationResult",
    "ElevationEstimationStrategy",
    "GeometricElevationEstimationStrategy",
    "DepthAnythingMappingStrategy",
    "DepthMappingFacade",
    "DepthMappingStrategy",
    "ClipLabelInpaintingVerificationStrategy",
    "GeminiInpaintingVerificationStrategy",
    "GeminiCutoutTiebreakStrategy",
    "GeminiCutoutAllCandidatesTiebreakStrategy",
    "INPAINT_VERIFY_CROP_PAD_RATIO",
    "InpaintSdParams",
    "InpaintingVerificationFacade",
    "InpaintingVerificationResult",
    "InpaintingVerificationStrategy",
    "crop_around_mask",
    "HybridInpaintingStrategy",
    "ImageInpaintingFacade",
    "ImageInpaintingStrategy",
    "ImageSegmentationFacade",
    "ImageSegmentationStrategy",
    "LamaInpaintingStrategy",
    "MaskSelectionTiebreakStrategy",
    "MaskSelectionStrategy",
    "AbsoluteClipGateStrategy",
    "RelativeClipRankingStrategy",
    "NearFarBlendedDepthMappingStrategy",
    "Metric3DNormalMappingStrategy",
    "NormalMappingFacade",
    "NormalMappingStrategy",
    "NovelViewFacade",
    "NovelViewStrategy",
    "StableZero123NovelViewError",
    "StableZero123NovelViewStrategy",
    "Hunyuan3D2GenerationError",
    "Hunyuan3D2ReconstructionStrategy",
    "OpenLrmReconstructionStrategy",
    "Reconstruction3DFacade",
    "Reconstruction3DStrategy",
    "ReconstructionQuality",
    "SamImageAdapter",
    "SamSegmentationStrategy",
    "StableDiffusionInpaintingStrategy",
    "TrellisReconstructionStrategy",
]
