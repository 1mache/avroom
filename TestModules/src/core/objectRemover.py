import os
import cv2
import logging
import numpy as np
from PIL import Image
from utils.DebugImageSaver import DebugImageSaver

# Configure logging
logger = logging.getLogger(__name__)

# Standard local imports 
from ai_engines.segmentation.SamFacadeSingleton import SamFacadeSingleton
from ai_engines.depth.OptimizedDepthFacade import OptimizedDepthFacade
from core.interfaces import IInpainter
from ai_engines.segmentation.SamImageAdapter import SamImageAdapter
from ai_engines.inpainting.HybridInpainter import HybridInpainter
from routing.boundary_variance_strategy import BoundaryVarianceRoutingStrategy

class ObjectRemover:
    def __init__(self):
        # AI Engines
        self.sam = SamFacadeSingleton()
        self.inpainter: IInpainter = HybridInpainter()
        
        # Architecture Components 
        self.depth_facade = OptimizedDepthFacade(threshold=100)
        self.sam_adapter = SamImageAdapter()
        self.router = BoundaryVarianceRoutingStrategy(sam_facade=self.sam)

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

    def remove_object(self, image_path: str, x: int, y: int, depth_output_flag=False):
        logger.info(f"Starting object removal - Image: {image_path}, Point: ({x}, {y})")
        
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
        
        print(f"[ObjectRemover] Requesting mask from SAM at ({x}, {y})...")
        mask = self.sam.get_mask_at_point(
            run_context['input_image'], 
            x, y, 
            expand_pixels=run_context['expand_pixels'],
            use_broad_mask=run_context['use_broad_mask'] 
        )
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

    def removeObjectTest(self):
        logger.info("removeObjectTest called")
        if self.image_path and self.point:
            self.remove_object(self.image_path, self.point[0], self.point[1], depth_output_flag=True)
        else:
            logger.warning("removeObjectTest called but image_path or point not set")
            print("[Error] Image path or point not set.")

    