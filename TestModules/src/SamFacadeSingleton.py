import os
import torch
from segment_anything import sam_model_registry, SamPredictor
from typing import Optional, List, Tuple
import numpy as np


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
        print(f"Loading SAM model on {device}...")
        
        sam = sam_model_registry["vit_b"](checkpoint=checkpoint_path)
        sam.to(device=device)
        self._predictor = SamPredictor(sam)
        print("SAM model loaded successfully!")

    def get_mask_at_point(self, image: np.ndarray, point: Tuple[int, int]) -> np.ndarray:
        """
        Get the best mask for a given point in the image.
        
        Args:
            image: Input image (numpy array)
            point: (x, y) coordinates in the image
            
        Returns:
            Binary mask as numpy array
        """
        self._predictor.set_image(image)
        input_point = np.array([[point[0], point[1]]])
        input_label = np.array([1])
        
        masks, scores, logits = self._predictor.predict(
            point_coords=input_point,
            point_labels=input_label,
            multimask_output=True
        )
        
        best_mask_idx = np.argmax(scores)
        return masks[best_mask_idx]

    def get_all_masks(self, image: np.ndarray) -> List[np.ndarray]:
        """
        Get masks for all items in the image using automatic mask generation.
        
        Args:
            image: Input image (numpy array)
            
        Returns:
            List of binary masks as numpy arrays
        """
        from segment_anything import SamAutomaticMaskGenerator
        
        mask_generator = SamAutomaticMaskGenerator(self._predictor.model)
        results = mask_generator.generate(image)
        
        return [result['segmentation'] for result in results]