from __future__ import annotations

import logging

import cv2
import numpy as np

from ....utils.debug_image_saver import DebugImageSaver
from ..depth_mapping_strategy import DepthMappingStrategy
from .near_far_blended_depth_mapping_strategy import NearFarBlendedDepthMappingStrategy

logger = logging.getLogger(__name__)

_DEPTH_MAP_OUTPUT_FOLDER = "outputs/depthMaps"


class EnhancedEdgeDepthMappingStrategy(DepthMappingStrategy):
    """Near/far blended depth map post-processed for sharp object-floor separation.

    Object-floor bleeding during SAM segmentation occurs when the blended depth
    map has low local contrast or soft transitions at the contact boundary between
    a foreground object and the floor plane — both surfaces may sit at similar
    depth values, causing SAM to treat them as one region.

    This strategy applies two sequential post-processing steps to the blended
    uint8 depth map produced by an inner :class:`DepthMappingStrategy`:

    1. **CLAHE (Contrast Limited Adaptive Histogram Equalization)** —
       ``cv2.createCLAHE`` divides the map into small tiles and equalises each
       independently, so a locally dark contact zone between object and floor is
       stretched to fill the full 0-255 range within that tile. The ``clipLimit``
       cap prevents over-amplification of noise in flat regions.

    2. **Bilateral Filter** — ``cv2.bilateralFilter`` smooths intra-surface
       depth texture while keeping high-gradient silhouette edges (the object
       outline, the floor boundary) sharp. The range kernel (``sigmaColor``)
       only blurs pixels whose depth values are close to each other; pixels
       across a strong edge are left uncoupled, which prevents them from
       "bleeding" into the floor region during inpainting/segmentation.

    The processing order — CLAHE then bilateral — is intentional: boosting
    local contrast first ensures the bilateral filter preserves those newly
    sharpened edges rather than averaging them away.

    Defaults reproduce production-safe settings. All parameters are
    configurable at construction time for A/B testing.

    Input/Output contract (unchanged from parent ABC):
        Input:  BGR ``np.ndarray`` H×W×3, uint8.
        Output: Single-channel ``np.ndarray`` H×W, uint8.
    """

    DEFAULT_CLAHE_CLIP_LIMIT: float = 2.0
    DEFAULT_CLAHE_TILE_GRID_SIZE: tuple[int, int] = (8, 8)
    DEFAULT_BILATERAL_D: int = 9
    DEFAULT_BILATERAL_SIGMA_COLOR: float = 75.0
    DEFAULT_BILATERAL_SIGMA_SPACE: float = 75.0

    def __init__(
        self,
        blend_strategy: DepthMappingStrategy | None = None,
        *,
        clahe_clip_limit: float = DEFAULT_CLAHE_CLIP_LIMIT,
        clahe_tile_grid_size: tuple[int, int] = DEFAULT_CLAHE_TILE_GRID_SIZE,
        bilateral_d: int = DEFAULT_BILATERAL_D,
        bilateral_sigma_color: float = DEFAULT_BILATERAL_SIGMA_COLOR,
        bilateral_sigma_space: float = DEFAULT_BILATERAL_SIGMA_SPACE,
        depth_map_saver: DebugImageSaver | None = None,
    ) -> None:
        """Initialise the strategy.

        Args:
            blend_strategy: Inner strategy that produces the base blended depth
                map. Defaults to :class:`NearFarBlendedDepthMappingStrategy`
                (near = Depth Anything V2 Small, far = LiheYoung Depth Anything
                Small) so this class is a drop-in enhancement of the default
                pipeline.
            clahe_clip_limit: Threshold for contrast limiting in CLAHE. Higher
                values allow more aggressive contrast boost but also amplify
                noise. 2.0 is a conservative production default.
            clahe_tile_grid_size: Number of tiles in each dimension for CLAHE.
                Smaller tiles yield finer local contrast adaptation. (8, 8) is
                appropriate for typical room-scale depth maps at 640×480+.
            bilateral_d: Diameter of the bilateral filter pixel neighbourhood.
                9 covers a ~4-pixel radius, sufficient to smooth sensor noise
                without blurring object outlines.
            bilateral_sigma_color: Range sigma for the bilateral filter. Controls
                how many depth-value units apart two pixels can be before they
                stop influencing each other. 75.0 allows smoothing within a
                ~30% depth band (on a 0-255 scale) without crossing edges.
            bilateral_sigma_space: Spatial sigma for the bilateral filter.
                Determines how far spatially a pixel can influence its
                neighbours. 75.0 provides broad spatial reach while the colour
                sigma keeps influence within the same depth layer.
            depth_map_saver: Optional saver for per-stage debug PNGs under
                ``TestModules/outputs/depthMaps/``. Defaults to a new
                :class:`DebugImageSaver` targeting that folder.
        """
        self._blend: DepthMappingStrategy = (
            blend_strategy or NearFarBlendedDepthMappingStrategy()
        )
        self._clahe_clip_limit = clahe_clip_limit
        self._clahe_tile_grid_size = clahe_tile_grid_size
        self._bilateral_d = bilateral_d
        self._bilateral_sigma_color = bilateral_sigma_color
        self._bilateral_sigma_space = bilateral_sigma_space
        self._depth_map_saver = depth_map_saver or DebugImageSaver(
            output_folder_name=_DEPTH_MAP_OUTPUT_FOLDER
        )

        logger.info(
            "EnhancedEdgeDepthMappingStrategy created "
            f"(blend={type(self._blend).__name__}, "
            f"clahe_clip_limit={clahe_clip_limit}, "
            f"clahe_tile_grid_size={clahe_tile_grid_size}, "
            f"bilateral_d={bilateral_d}, "
            f"bilateral_sigma_color={bilateral_sigma_color}, "
            f"bilateral_sigma_space={bilateral_sigma_space})"
        )

    def _save_stage_depth(self, stage_name: str, depth: np.ndarray) -> None:
        """Persist an intermediate depth map for visual inspection."""
        filepath = self._depth_map_saver.save(f"enhanced_edge_{stage_name}", depth)
        if filepath:
            logger.debug(f"[EnhancedEdge] saved stage '{stage_name}': {filepath}")

    def map_depth(self, image: np.ndarray) -> np.ndarray:
        """Produce a contrast-enhanced, edge-preserved depth map for ``image``.

        Args:
            image: Input BGR ``np.ndarray`` (H×W×3), uint8.

        Returns:
            2-D uint8 ``np.ndarray`` (H×W) with sharpened object-floor
            boundaries suitable for SAM input.
        """
        # --- Stage 1: base blended depth map ---------------------------------
        depth: np.ndarray = self._blend.map_depth(image)
        logger.debug(
            f"[EnhancedEdge] blend output: shape={depth.shape} dtype={depth.dtype}"
        )

        # Collapse to single channel if the inner strategy returns a 3-channel
        # array — mirrors the dimension guard in NearFarBlendedDepthMappingStrategy.
        if depth.ndim == 3:
            depth = cv2.cvtColor(depth, cv2.COLOR_RGB2GRAY)
            logger.debug(
                f"[EnhancedEdge] converted 3-channel to grayscale: shape={depth.shape}"
            )

        self._save_stage_depth("01_blended", depth)

        # --- Stage 2: full-range normalisation --------------------------------
        # Guarantee 0-255 coverage so CLAHE tiles start from a common baseline.
        depth = cv2.normalize(depth, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)  # type: ignore[call-overload]
        logger.debug(
            f"[EnhancedEdge] after normalise: min={depth.min()} max={depth.max()}"
        )
        self._save_stage_depth("02_normalized", depth)

        # --- Stage 3: CLAHE ---------------------------------------------------
        # Adaptive per-tile histogram equalisation maximises local contrast at
        # the object-floor contact zone even when global depth range is wide.
        # The clip limit prevents noise amplification in flat depth regions
        # (walls, ceilings) where little true geometry variation exists.
        clahe = cv2.createCLAHE(
            clipLimit=self._clahe_clip_limit,
            tileGridSize=self._clahe_tile_grid_size,
        )
        depth = clahe.apply(depth)
        logger.debug(
            f"[EnhancedEdge] after CLAHE: min={depth.min()} max={depth.max()}"
        )
        self._save_stage_depth("03_clahe", depth)

        # --- Stage 4: bilateral filter ----------------------------------------
        # Edge-preserving smoothing: pixels with similar depth values are
        # averaged (removing intra-surface noise / texture), while pixels
        # across a depth edge remain decoupled, keeping silhouettes sharp and
        # preventing them from blurring into the floor layer.
        depth = cv2.bilateralFilter(
            depth,
            d=self._bilateral_d,
            sigmaColor=self._bilateral_sigma_color,
            sigmaSpace=self._bilateral_sigma_space,
        )
        logger.debug(
            f"[EnhancedEdge] after bilateral: shape={depth.shape} dtype={depth.dtype}"
        )
        self._save_stage_depth("04_bilateral", depth)

        return depth.astype(np.uint8)
