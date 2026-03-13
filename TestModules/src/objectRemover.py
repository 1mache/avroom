import os
import cv2
import logging
import numpy as np
from PIL import Image

# Configure logging
logger = logging.getLogger(__name__)

# Standard local imports 
from SamFacadeSingleton import SamFacadeSingleton
from OptimizedDepthFacade import OptimizedDepthFacade
from interfaces import IInpainter
from SamImageAdapter import SamImageAdapter
from HybridInpainter import HybridInpainter

class ObjectRemover:
    def __init__(self):
        # AI Engines
        self.sam = SamFacadeSingleton()
        self.inpainter: IInpainter = HybridInpainter()
        
        # Architecture Components 
        self.depth_facade = OptimizedDepthFacade(threshold=100)
        self.sam_adapter = SamImageAdapter()
        
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
        self._save_intermediate("optimized_depth", optimized_depth)

        if depth_output_flag:
            self._save_depth_debug(optimized_depth)

        # 2. Adapter with Cache
        logger.info("Step 2: Adapting data...")
        adapted_for_sam = self.sam_adapter.get_adapted_image(
            raw_data=optimized_depth,
            image_id=image_path,
            point=(x, y)
        )
        self._save_intermediate("adapted_for_sam", adapted_for_sam)

        # 3. SAM Mask 
        logger.info(f"Step 3: Computing SAM mask at ({x}, {y}) on pure depth map...")
        print(f"[ObjectRemover] Requesting mask from SAM at ({x}, {y})...")
        
        mask = self.sam.get_mask_at_point(adapted_for_sam, x, y) 
        self._save_intermediate("mask", mask, is_mask=True)

        # 4. Inpaint 
        logger.info("Step 4: Inpainting image using the isolated pipeline...")
        # The Controller delegates the inpainting task to the interface.
        # It is completely blind to the fact that two models are running sequentially.
        result_image = self.inpainter.inpaint(image, mask)
        
        self._save_result(result_image)
        logger.info("Object removal completed successfully")

    def removeObjectTest(self):
        logger.info("removeObjectTest called")
        if self.image_path and self.point:
            self.remove_object(self.image_path, self.point[0], self.point[1], depth_output_flag=True)
        else:
            logger.warning("removeObjectTest called but image_path or point not set")
            print("[Error] Image path or point not set.")

    def _save_intermediate(self, function_name: str, data: np.ndarray, is_mask: bool = False):
        output_dir = os.path.join(os.path.dirname(__file__), "..", "outputs")
        os.makedirs(output_dir, exist_ok=True)
        
        save_data = data.copy()
        if is_mask:
            if save_data.dtype == bool or save_data.max() <= 1.0:
                save_data = (save_data * 255).astype(np.uint8)
            else:
                save_data = save_data.astype(np.uint8)
        
        out_path = os.path.join(output_dir, f"{function_name}.png")
        cv2.imwrite(out_path, save_data)
        logger.debug(f"Saved intermediate result: {function_name} to {out_path}")
        print(f"[ObjectRemover] Saved {function_name} to {out_path}")

    def _save_depth_debug(self, depth_map: np.ndarray):
        output_dir = os.path.join(os.path.dirname(__file__), "..", "outputs", "depthMaps")
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, "optimized_hybrid_depth.png")
        cv2.imwrite(out_path, depth_map)
        logger.debug(f"Saved debug depth map to {out_path}")

    def _save_result(self, result: np.ndarray):
        output_dir = os.path.join(os.path.dirname(__file__), "..", "outputs")
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, "final_removed_object.png")
        cv2.imwrite(out_path, result)
        logger.info(f"Final result saved to {out_path}")