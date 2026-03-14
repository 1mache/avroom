import cv2
import numpy as np

class MaskRefiner:
    """
    Responsible for post-processing and refining segmentation masks.
    Prepares masks for downstream tasks like inpainting by applying
    morphological operations (e.g., dilation to avoid halo effects).
    """
    def __init__(self):
        pass

    def dilate_mask(self, mask: np.ndarray, pixels: int = 8) -> np.ndarray:
        """
        Expands the mask by a given number of pixels using dilation.
        Uses a circular/elliptical kernel for smooth, organic expansion.
        """
        if pixels <= 0:
            return mask
            
        # Ensure kernel size is an odd number for perfect symmetry
        kernel_size = int(pixels)
        if kernel_size % 2 == 0:
            kernel_size += 1
            
        # Create a circular (ellipse) kernel instead of a square one!
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        
        # Convert boolean mask to uint8 for OpenCV
        mask_uint8 = mask.astype(np.uint8)
        
        # Apply morphological dilation
        dilated_mask = cv2.dilate(mask_uint8, kernel, iterations=1)
        
        # Convert back to boolean mask
        return dilated_mask.astype(bool)