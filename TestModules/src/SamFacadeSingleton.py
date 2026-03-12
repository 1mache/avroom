import os
import torch
import logging
from segment_anything import sam_model_registry, SamPredictor
from typing import Optional, List, Tuple
import numpy as np

# Configure logging
logger = logging.getLogger(__name__)


class SamFacadeSingleton:
    _instance: Optional['SamFacadeSingleton'] = None
    _predictor: Optional[SamPredictor] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SamFacadeSingleton, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize the SAM model and load checkpoint."""
        # 1. מציאת הנתיב המוחלט של התיקייה הנוכחית (src)
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        
        # 2. הרכבת הנתיב המדויק לתיקיית checkpoints
        checkpoint_path = os.path.join(BASE_DIR, "..", "checkpoints", "sam_vit_b_01ec64.pth")
        
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"SamFacadeSingleton initializing on {device}")
        print(f"Loading SAM model on {device}...")
        
        sam = sam_model_registry["vit_b"](checkpoint=checkpoint_path)
        sam.to(device=device)
        self._predictor = SamPredictor(sam)
        logger.info("SAM model loaded successfully")
        print("SAM model loaded successfully!")

    def get_mask_at_point(self, image: np.ndarray, x: int, y: int) -> np.ndarray:
        """
        Generates a single mask for a specific pixel coordinate.
        """
        logger.debug(f"Getting SAM mask at point ({x}, {y})")
        # Ensure the image is set in the SAM predictor
        # Use _predictor (with underscore) as defined in your class __init__
        self._predictor.set_image(image)
        
        # Prepare input point and label (1 for foreground)
        input_point = np.array([[x, y]])
        input_label = np.array([1])
        
        # Predict masks based on the point
        masks, scores, logits = self._predictor.predict(
            point_coords=input_point,
            point_labels=input_label,
            multimask_output=False,
        )
        
        logger.debug(f"SAM mask generated successfully")
        # Return the best mask found (the first one in the array)
        return masks[0]

    def get_all_masks(self, image: np.ndarray) -> List[np.ndarray]:
        """
        Get masks for all items in the image using automatic mask generation.
        
        Args:
            image: Input image (numpy array)
            
        Returns:
            List of binary masks as numpy arrays
        """
        logger.info("Generating masks for all objects using automatic mask generation")
        from segment_anything import SamAutomaticMaskGenerator
        
        mask_generator = SamAutomaticMaskGenerator(self._predictor.model)
        results = mask_generator.generate(image)
        logger.info(f"Generated {len(results)} masks")
        
        return [result['segmentation'] for result in results]