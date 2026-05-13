from __future__ import annotations

import logging

import cv2
import numpy as np

from ..ai_engines.depth.depth_mapping_facade import DepthMappingFacade
from ..ai_engines.inpainting.image_inpainting_facade import ImageInpaintingFacade
from ..ai_engines.segmentation.image_segmentation_facade import ImageSegmentationFacade
from ..ai_engines.segmentation.sam_image_adapter import SamImageAdapter
from ..routing.segmentation_routing_strategy import SegmentationRoutingStrategy
from ..routing.strategies.boundary_variance_routing_strategy import (
    BoundaryVarianceRoutingStrategy,
)
from ..utils.bgra_cutout_composer import BgraCutoutComposer
from ..utils.debug_image_saver import DebugImageSaver
from ..utils.mask_refiner import MaskRefiner

logger = logging.getLogger(__name__)


def _ensure_mask_hw(mask: np.ndarray, target_hw: tuple[int, int]) -> np.ndarray:
    """Resize ``mask`` to ``target_hw`` with nearest-neighbor; keep binary semantics."""
    h, w = target_hw

    if mask.ndim == 3:
        mask = mask[:, :, 0]

    if mask.shape[:2] != (h, w):
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)

    if mask.dtype == bool:
        return mask

    thresh = 0.5 if float(mask.max()) <= 1.0 else 127
    return (mask > thresh).astype(np.uint8) * 255


class ObjectRemover:
    """Master Facade orchestrating the full object-removal pipeline.

    The class composes one Facade per AI domain (depth mapping, segmentation,
    inpainting) plus a routing strategy that decides how to invoke
    segmentation. Every collaborator is injected via the constructor with a
    sensible default, so ``ObjectRemover()`` with no arguments still works
    (this is how FastAPI's ``segment_at_click`` currently uses it).

    Pipeline steps performed by :meth:`remove_object`:

    1. Depth mapping  - :class:`DepthMappingFacade` produces a uint8 depth map.
    2. Adapt          - :class:`SamImageAdapter` makes the depth map SAM-friendly.
    3. Route          - :class:`SegmentationRoutingStrategy` decides expansion etc.
    4. Segment        - :class:`ImageSegmentationFacade` returns a tight mask.
    5. Refine         - :class:`MaskRefiner` applies a small uniform dilation.
    6. Inpaint        - :class:`ImageInpaintingFacade` fills the mask region.
    7. Compose cutout - :class:`BgraCutoutComposer` extracts the original
       overlap as BGRA with alpha=0 outside the mask.

    Returns ``(background_bgr, cutout_bgra)`` numpy arrays - the contract
    consumed by :func:`fastApi-app/core/image_processing.segment_at_click`.
    """

    def __init__(
        self,
        depth_facade: DepthMappingFacade | None = None,
        segmentation_facade: ImageSegmentationFacade | None = None,
        inpainting_facade: ImageInpaintingFacade | None = None,
        routing_strategy: SegmentationRoutingStrategy | None = None,
        sam_adapter: SamImageAdapter | None = None,
        mask_refiner: MaskRefiner | None = None,
        debug_image_saver: DebugImageSaver | None = None,
    ) -> None:
        self.depth: DepthMappingFacade = depth_facade or DepthMappingFacade()
        self.segmentation: ImageSegmentationFacade = (
            segmentation_facade or ImageSegmentationFacade()
        )
        self.inpainting: ImageInpaintingFacade = (
            inpainting_facade or ImageInpaintingFacade()
        )
        # Routing depends on segmentation, so build it after - and reuse the
        # same segmentation facade so there's only one SAM in play.
        self.router: SegmentationRoutingStrategy = (
            routing_strategy or BoundaryVarianceRoutingStrategy(self.segmentation)
        )
        self.sam_adapter: SamImageAdapter = sam_adapter or SamImageAdapter()
        self.mask_refiner: MaskRefiner = mask_refiner or MaskRefiner(depth_tolerance=10)
        self.image_saver: DebugImageSaver = debug_image_saver or DebugImageSaver()

        self.image_path: str | None = None
        self.point: tuple[int, int] | None = None
        logger.info("ObjectRemover initialized")

    def set_image(self, image_path: str) -> None:
        self.image_path = image_path
        logger.debug(f"Image path set to: {image_path}")

    def set_point(self, x: int, y: int) -> None:
        self.point = (x, y)
        logger.debug(f"Click point set to: ({x}, {y})")

    def remove_object(
        self,
        image_path: str,
        x: int,
        y: int,
        depth_output_flag: bool = False,
        image_bytes: bytes | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Run the full pipeline and return ``(background_bgr, cutout_bgra)``."""
        logger.info(f"Starting object removal - Image: {image_path}, Point: ({x}, {y})")

        if image_bytes is not None:
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if image is None:
                logger.error("Could not decode image bytes for inpaint pipeline")
                raise ValueError("Could not decode image bytes into an image array")
        else:
            image = cv2.imread(image_path)
            if image is None:
                logger.error(f"Could not load image: {image_path}")
                raise FileNotFoundError(f"Could not load image: {image_path}")

        logger.info("Step 1: Computing optimized depth map...")
        optimized_depth = self.depth.map_depth(image)
        self.image_saver.save("optimized_depth", optimized_depth)

        logger.info("Step 2: Adapting data...")
        adapted_for_sam = self.sam_adapter.get_adapted_image(
            raw_data=optimized_depth,
            image_id=image_path,
            point=(x, y),
        )
        self.image_saver.save("adapted_for_sam", adapted_for_sam)

        logger.info(f"Step 3: Determining optimal context for ({x}, {y})...")
        run_context = self.router.choose_input(
            rgb_image=image,
            raw_depth=optimized_depth,
            adapted_depth=adapted_for_sam,
            x=x,
            y=y,
        )

        # Tight mask first - we don't want to accidentally include nearby
        # background objects. The post-mask uniform dilation handles small
        # edge misses.
        logger.info(f"Requesting TIGHT mask from SAM at ({x}, {y})...")
        tight_mask, original_mask = self.segmentation.get_mask_at_point(
            run_context["input_image"],
            x,
            y,
            expand_pixels=run_context.get("expand_pixels", 14),
            use_broad_mask=run_context["use_broad_mask"],
        )
        tight_mask = _ensure_mask_hw(tight_mask, image.shape[:2])
        original_mask = _ensure_mask_hw(original_mask, image.shape[:2])
        self.image_saver.save("tight_mask", tight_mask)

        logger.info("Generating debug tight mask overlay (Whitened Image, pre-refinement)...")
        tight_overlay = image.copy()
        tight_bool_mask = tight_mask > 0 if tight_mask.dtype != bool else tight_mask
        tight_overlay[tight_bool_mask] = [255, 255, 255]
        self.image_saver.save("debug_tight_mask_overlay", tight_overlay)

        logger.info("Refining mask using simple uniform dilation (~3px expansion)...")
        mask = self.mask_refiner.expand_mask_uniform(
            original_mask=tight_mask,
            radius=3,
        )
        mask = _ensure_mask_hw(mask, image.shape[:2])
        self.image_saver.save("mask", mask)

        logger.info("Generating debug mask overlay (Whitened Image)...")
        mask_overlay = image.copy()
        bool_mask = mask > 0 if mask.dtype != bool else mask
        mask_overlay[bool_mask] = [255, 255, 255]
        self.image_saver.save("debug_mask_overlay", mask_overlay)

        logger.info("Step 4: Inpainting image using isolated pipeline...")
        result_image = self.inpainting.inpaint(
            image,
            mask,
            strength=run_context["sd_strength"],
        )
        self.image_saver.save("final_removed_object", result_image)
        logger.info("Object removal completed successfully")

        if mask is None:
            raise ValueError("Internal error: mask is None after mask refinement.")

        cutout_bgra = BgraCutoutComposer.compose_original_overlap_bgra(
            original_bgr=image,
            mask=original_mask,
        )

        return result_image, cutout_bgra

    def remove_object_test(self) -> tuple[np.ndarray, np.ndarray] | None:
        """Run :meth:`remove_object` using state set via :meth:`set_image`/
        :meth:`set_point`. Returns ``None`` if either is missing.
        """
        logger.info("remove_object_test called")
        if self.image_path and self.point:
            return self.remove_object(
                self.image_path,
                self.point[0],
                self.point[1],
                depth_output_flag=True,
            )

        logger.warning(
            "remove_object_test called but image_path or point not set"
        )
        return None
