import os
import cv2
import logging
import numpy as np
from PIL import Image
from utils.DebugImageSaver import DebugImageSaver
from utils.MaskRefiner import MaskRefiner
from utils.MaskOverlapRGBAComposer import MaskOverlapRGBAComposer

# Configure logging
logger = logging.getLogger(__name__)


def _ensure_mask_hw(mask: np.ndarray, target_hw: tuple[int, int]) -> np.ndarray:
    """Resize mask to target (H, W) using nearest-neighbor and keep binary semantics."""
    h, w = target_hw

    if mask.ndim == 3:
        # If mask accidentally has channels, collapse to first channel.
        mask = mask[:, :, 0]

    if mask.shape[:2] != (h, w):
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)

    if mask.dtype == bool:
        return mask

    thresh = 0.5 if float(mask.max()) <= 1.0 else 127
    return (mask > thresh).astype(np.uint8) * 255

# Standard local imports 
from ai_engines.segmentation.SamFacadeSingleton import SamFacadeSingleton
from ai_engines.depth.OptimizedDepthFacade import OptimizedDepthFacade
from core.interfaces import IInpainter
from ai_engines.segmentation.SamImageAdapter import SamImageAdapter
from ai_engines.inpainting.HybridInpainter import HybridInpainter
from routing.boundary_variance_strategy import BoundaryVarianceRoutingStrategy
from routing.gradient_variance_routing_strategy import GradientVarianceRoutingStrategy

class ObjectRemover:
    def __init__(self):
        # AI Engines
        self.sam = SamFacadeSingleton()
        self.inpainter: IInpainter = HybridInpainter()
        
        # Architecture Components 
        self.depth_facade = OptimizedDepthFacade(threshold=100)
        self.sam_adapter = SamImageAdapter()
        self.router = BoundaryVarianceRoutingStrategy(sam_facade=self.sam)
        self.mask_refiner = MaskRefiner(depth_tolerance=10)

        self.image_saver = DebugImageSaver()
        
        self.image_path = None
        self.point = None
        logger.info("ObjectRemover initialized")

    def set_image(self, image_path: str):
        self.image_path = image_path
        logger.debug(f"Image path set to: {image_path}")

    def set_point(self, x: int, y: int):
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
        logger.info(f"Starting object removal - Image: {image_path}, Point: ({x}, {y})")
        if image_bytes is not None:
            # Decode uploaded image bytes into an OpenCV BGR array.
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

        # 1. Depth Facade
        logger.info("Step 1: Computing optimized depth map...")
        optimized_depth = self.depth_facade.get_optimized_depth_map(image)
        self.image_saver.save("optimized_depth", optimized_depth)
        

        # 2. Adapter with Cache
        logger.info("Step 2: Adapting data...")
        adapted_for_sam = self.sam_adapter.get_adapted_image(
            raw_data=optimized_depth,
            image_id=image_path,
            point=(x, y)
        )
        self.image_saver.save("adapted_for_sam", adapted_for_sam)

       # 3. Dynamic Routing & SAM Mask 
        logger.info(f"Step 3: Determining optimal context for ({x}, {y})...")
        
        run_context = self.router.choose_input(
            rgb_image=image, 
            raw_depth=optimized_depth, 
            adapted_depth=adapted_for_sam, 
            x=x, y=y
        )
        
        # --- שלב 1: מבקשים מ-SAM מסכה צמודה והדוקה (0 הרחבה) ---
        logger.info(f"Requesting TIGHT mask from SAM at ({x}, {y})...")
        tight_mask = self.sam.get_mask_at_point(
            run_context['input_image'], 
            x, y, 
            expand_pixels=run_context.get('expand_pixels', 14),
            use_broad_mask=run_context['use_broad_mask'] 
        )
        tight_mask = _ensure_mask_hw(tight_mask, image.shape[:2])
        self.image_saver.save("tight_mask", tight_mask)

        # ==========================================
        # DEBUG: Generate Whitened Overlay for TIGHT Mask (pre-refinement)
        # ==========================================
        logger.info("Generating debug tight mask overlay (Whitened Image, pre-refinement)...")
        tight_overlay = image.copy()
        tight_bool_mask = tight_mask > 0 if tight_mask.dtype != bool else tight_mask
        tight_overlay[tight_bool_mask] = [255, 255, 255]
        self.image_saver.save("debug_tight_mask_overlay", tight_overlay)
        # ==========================================

        # --- שלב 2: ניפוח מסכה פשוט ואחיד (2–3 פיקסלים לכל הכיוונים) ---
        logger.info("Refining mask using simple uniform dilation (~3px expansion)...")
        mask = self.mask_refiner.expand_mask_uniform(
            original_mask=tight_mask,
            radius=3
        )
        mask = _ensure_mask_hw(mask, image.shape[:2])
        
        # שמירת המסכה המדויקת לדיבוג
        self.image_saver.save("mask", mask)

        # ==========================================
        # DEBUG: Generate Whitened Mask Overlay
        # ==========================================
        logger.info("Generating debug mask overlay (Whitened Image)...")
        mask_overlay = image.copy()
        # Convert mask to boolean if it isn't already, for NumPy indexing
        bool_mask = mask > 0 if mask.dtype != bool else mask
        # Paint the masked area pure white
        mask_overlay[bool_mask] = [255, 255, 255]
        self.image_saver.save("debug_mask_overlay", mask_overlay)
        # ==========================================

       # 4. Inpaint 
        logger.info("Step 4: Inpainting image using isolated pipeline...")
        
        # Pass the dynamic strength calculated by the router to the inpainting engine
        result_image = self.inpainter.inpaint(
            image, 
            mask, 
            strength=run_context['sd_strength'] 
        )

        self.image_saver.save("final_removed_object", result_image)
        logger.info("Object removal completed successfully")

        # Return:
        # 1) final_removed_object: inpainted result (BGR uint8)
        # 2) original image with only mask-overlapping pixels visible (BGRA, alpha=0 elsewhere)
        if mask is None:
            raise ValueError("Internal error: mask is None after mask refinement.")

        original_bg_ra = MaskOverlapRGBAComposer.compose_original_overlap_bgra(
            original_bgr=image,
            mask=mask,
        )

        return result_image, original_bg_ra

    def removeObjectTest(self) -> tuple[np.ndarray, np.ndarray] | None:
        logger.info("removeObjectTest called")
        if self.image_path and self.point:
            return self.remove_object(
                self.image_path,
                self.point[0],
                self.point[1],
                depth_output_flag=True,
            )
        else:
            logger.warning("removeObjectTest called but image_path or point not set")
            print("[Error] Image path or point not set.")
            return None

    