from __future__ import annotations

import logging

import cv2
import numpy as np

from ..ai_engines.depth.depth_mapping_facade import DepthMappingFacade
from ..ai_engines.segmentation.image_segmentation_facade import ImageSegmentationFacade
from ..ai_engines.segmentation.sam_image_adapter import SamImageAdapter
from ..routing.segmentation_routing_strategy import SegmentationRoutingStrategy
from ..routing.strategies.boundary_variance_routing_strategy import (
    BoundaryVarianceRoutingStrategy,
)
from ..utils.bgra_cutout_composer import BgraCutoutComposer
from ..utils.debug_image_saver import DebugImageSaver
from ..utils.mask_refiner import MaskRefiner
from ._mask_utils import ensure_mask_hw

logger = logging.getLogger(__name__)


class ObjectSegmentor:
    """Segmentation-only facade that returns every SAM candidate for a click.

    Runs stages 1–3 and 5–7 of the full object-removal pipeline (depth →
    adapt → route → multi-mask segment → refine → compose cutout) but
    deliberately omits stage 4 (inpainting). The returned masks are ready
    to be passed directly to :class:`BackgroundInpainter` when inpainting is
    required later.

    Constructor dependencies follow the same injection pattern as
    :class:`ObjectRemover`: every collaborator has a sensible default so
    ``ObjectSegmentor()`` works with no arguments.

    Primary entry point: :meth:`get_mask_for_object_at_position`.
    """

    def __init__(
        self,
        depth_facade: DepthMappingFacade | None = None,
        segmentation_facade: ImageSegmentationFacade | None = None,
        routing_strategy: SegmentationRoutingStrategy | None = None,
        sam_adapter: SamImageAdapter | None = None,
        mask_refiner: MaskRefiner | None = None,
        debug_image_saver: DebugImageSaver | None = None,
    ) -> None:
        self.depth: DepthMappingFacade = depth_facade or DepthMappingFacade()
        self.segmentation: ImageSegmentationFacade = (
            segmentation_facade or ImageSegmentationFacade()
        )
        # Routing depends on segmentation — reuse the same facade so there is
        # only one SAM predictor instance in play.
        self.router: SegmentationRoutingStrategy = (
            routing_strategy or BoundaryVarianceRoutingStrategy(self.segmentation)
        )
        self.sam_adapter: SamImageAdapter = sam_adapter or SamImageAdapter()
        self.mask_refiner: MaskRefiner = mask_refiner or MaskRefiner(depth_tolerance=10)
        self.image_saver: DebugImageSaver = debug_image_saver or DebugImageSaver()
        logger.info("ObjectSegmentor initialized")

    def get_mask_for_object_at_position(
        self,
        image_path: str,
        x: int,
        y: int,
        image_bytes: bytes | None = None,
    ) -> tuple[tuple[np.ndarray, np.ndarray], ...]:
        """Segment all SAM candidates at ``(x, y)`` and return refined mask pairs.

        Executes the pipeline up to and including mask refinement and cutout
        composition for every candidate the segmentation strategy produces.
        Inpainting is intentionally omitted — pass any ``refined_mask`` from
        the returned pairs to :meth:`BackgroundInpainter.cut_mask_from_image`
        when the background fill is also needed.

        Args:
            image_path: Filesystem path or synthetic cache key
                (e.g. ``memory://<sha256>`` when FastAPI supplies bytes).
            x: Click X coordinate in image pixel space.
            y: Click Y coordinate in image pixel space.
            image_bytes: Optional raw image bytes. When provided the image is
                decoded from memory instead of read from ``image_path``.

        Returns:
            A tuple of ``(refined_mask, cutout_bgra)`` pairs from **both** passes
            concatenated: depth-map candidates first, then original-image candidates.
            ``refined_mask`` is the routing-expanded mask after a 3 px uniform
            dilation (ready for inpainting). ``cutout_bgra`` is the original pixels
            inside the *raw* SAM mask with alpha = 0 outside it (BGRA, same spatial
            size as the input image).
        """
        logger.info(
            f"Starting multi-mask segmentation — image: {image_path}, point: ({x}, {y})"
        )

        if image_bytes is not None:
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if image is None:
                logger.error("Could not decode image bytes for segmentation pipeline")
                raise ValueError("Could not decode image bytes into an image array")
        else:
            image = cv2.imread(image_path)
            if image is None:
                logger.error(f"Could not load image: {image_path}")
                raise FileNotFoundError(f"Could not load image: {image_path}")

        logger.info("Step 1: Computing optimized depth map...")
        optimized_depth = self.depth.map_depth(image)
        # Depth is already persisted by EnhancedEdgeDepthMappingStrategy as
        # outputs/depthMaps/enhanced_edge_04_bilateral.png — no duplicate save here.

        logger.info("Step 2: Adapting depth data for SAM...")
        adapted_for_sam = self.sam_adapter.get_adapted_image(
            raw_data=optimized_depth,
            image_id=image_path,
            point=(x, y),
        )
        self.image_saver.save("segment_adapted_depth_for_sam", adapted_for_sam)

        logger.info(f"Step 3: Determining optimal routing context for ({x}, {y})...")
        run_context = self.router.choose_input(
            rgb_image=image,
            raw_depth=optimized_depth,
            adapted_depth=adapted_for_sam,
            x=x,
            y=y,
        )

        logger.info("Pass A (depth): requesting ALL candidate masks from SAM...")
        depth_candidate_pairs = self.segmentation.get_all_masks_for_position(
            run_context["input_image"],
            x,
            y,
            expand_pixels=run_context.get("expand_pixels", 14),
            use_broad_mask=run_context["use_broad_mask"],
        )
        depth_pairs = self._process_candidates(depth_candidate_pairs, image, label="depth_pass")
        logger.info(f"Pass A (depth): {len(depth_pairs)} candidate(s) produced")

        logger.info("Pass B (image): requesting ALL candidate masks from SAM on original RGB...")
        image_candidate_pairs = self.segmentation.get_all_masks_for_position(
            image,
            x,
            y,
            expand_pixels=14,
            use_broad_mask=False,
        )
        image_pairs = self._process_candidates(image_candidate_pairs, image, label="image_pass")
        logger.info(f"Pass B (image): {len(image_pairs)} candidate(s) produced")

        result_pairs = depth_pairs + image_pairs
        logger.info(
            f"Multi-mask segmentation completed — {len(result_pairs)} total candidate(s) "
            f"({len(depth_pairs)} depth + {len(image_pairs)} image)"
        )
        return tuple(result_pairs)

    def _process_candidates(
        self,
        candidate_pairs: tuple[tuple[np.ndarray, np.ndarray], ...],
        image: np.ndarray,
        label: str,
    ) -> list[tuple[np.ndarray, np.ndarray]]:
        """Process SAM candidate mask pairs into refined masks and BGRA cutouts.

        Runs the refine-and-compose stage on every ``(expanded_mask, original_mask)``
        pair produced by SAM. Both passes (depth and image) delegate here so the
        processing logic stays in one place.

        Args:
            candidate_pairs: Raw ``(expanded_mask, original_mask)`` pairs from SAM.
            image: Original BGR image used for cutout composition and overlays.
            label: Short string prefix (e.g. ``"depth"`` or ``"image"``) applied to
                all debug-image save keys so the two passes never overwrite each other.

        Returns:
            List of ``(refined_mask, cutout_bgra)`` pairs ready for inpainting or
            direct consumption by the caller.
        """
        result_pairs: list[tuple[np.ndarray, np.ndarray]] = []
        total_candidates = len(candidate_pairs)

        for candidate_index, (expanded_mask, original_mask) in enumerate(candidate_pairs):
            pfx = f"{label}_candidate_{candidate_index}"
            logger.info(
                f"[{label}] Processing SAM candidate {candidate_index + 1}/{total_candidates}..."
            )

            expanded_mask = ensure_mask_hw(expanded_mask, image.shape[:2])
            original_mask = ensure_mask_hw(original_mask, image.shape[:2])

            # Raw mask as SAM produced it (before routing dilation).
            self.image_saver.save(f"{pfx}_sam_raw_mask", original_mask)

            # Mask after routing-dilation (expand_pixels applied by SAM strategy).
            self.image_saver.save(f"{pfx}_sam_expanded_mask", expanded_mask)

            expanded_bool = expanded_mask > 0 if expanded_mask.dtype != bool else expanded_mask
            expanded_overlay = image.copy()
            expanded_overlay[expanded_bool] = [255, 255, 255]
            self.image_saver.save(f"{pfx}_overlay_expanded", expanded_overlay)

            # Uniform 3 px dilation on top of the routing-expanded mask.
            refined_mask = self.mask_refiner.expand_mask_uniform(
                original_mask=expanded_mask,
                radius=3,
            )
            refined_mask = ensure_mask_hw(refined_mask, image.shape[:2])

            # refined_mask is a return value — save it explicitly.
            self.image_saver.save(f"{pfx}_refined_mask", refined_mask)

            refined_bool = refined_mask > 0 if refined_mask.dtype != bool else refined_mask
            refined_overlay = image.copy()
            refined_overlay[refined_bool] = [255, 255, 255]
            self.image_saver.save(f"{pfx}_overlay_refined", refined_overlay)

            # cutout_bgra is a return value — save it explicitly.
            cutout_bgra = BgraCutoutComposer.compose_original_overlap_bgra(
                original_bgr=image,
                mask=original_mask,
            )
            self.image_saver.save(f"{pfx}_cutout_bgra", cutout_bgra)

            result_pairs.append((refined_mask, cutout_bgra))
            logger.debug(
                f"[{label}] Candidate {candidate_index}: "
                f"refined_mask shape={refined_mask.shape}, cutout_bgra shape={cutout_bgra.shape}"
            )

        return result_pairs
