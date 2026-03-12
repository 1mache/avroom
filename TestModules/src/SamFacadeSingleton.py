import os
import torch
import logging
import numpy as np
from segment_anything import sam_model_registry, SamPredictor

# הייבוא החדש של המחלקה שיצרנו
from MaskRefiner import MaskRefiner

logger = logging.getLogger(__name__)

class SamFacadeSingleton:
    """
    Singleton Facade for the Segment Anything Model (SAM).
    Composed with a MaskRefiner to handle post-processing.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SamFacadeSingleton, cls).__new__(cls)
            cls._instance._is_initialized = False
        return cls._instance

    def __init__(self):
        if not self._is_initialized:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"SamFacadeSingleton initializing on {device}")
            
            # --- הגדרת נתיב המודל ---
            current_dir = os.path.dirname(os.path.abspath(__file__))
            checkpoint_path = os.path.join(current_dir, "..", "checkpoints", "sam_vit_b_01ec64.pth")
            model_type = "vit_b"
            
            try:
                # 1. Loading the AI Engine
                sam = sam_model_registry[model_type](checkpoint=checkpoint_path)
                sam.to(device=device)
                self._predictor = SamPredictor(sam)
                
                # 2. Composition: Injecting the MaskRefiner component
                self.mask_refiner = MaskRefiner()
                
                logger.info("SAM model loaded successfully")
                self._is_initialized = True
            except Exception as e:
                logger.error(f"Error loading SAM model: {e}")
                raise

    def get_mask_at_point(self, image: np.ndarray, x: int, y: int, expand_pixels: int = 8) -> np.ndarray:
        """
        Generates a mask for a specific pixel and refines it via the composed MaskRefiner.
        """
        logger.debug(f"Getting SAM mask at point ({x}, {y})")
        
        self._predictor.set_image(image)
        
        input_point = np.array([[x, y]])
        input_label = np.array([1])
        
        # AI Prediction
        masks, scores, logits = self._predictor.predict(
            point_coords=input_point,
            point_labels=input_label,
            multimask_output=False,
        )
        
        raw_mask = masks[0]

        # Post-Processing via Composition
        refined_mask = self.mask_refiner.dilate_mask(raw_mask, pixels=expand_pixels)
            
        logger.debug("SAM mask generated and refined successfully")
        return refined_mask