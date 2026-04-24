import numpy as np
import logging
import cv2
from PIL import Image
from simple_lama_inpainting import SimpleLama
from ...core.interfaces import IInpainter

# Configure logging
logger = logging.getLogger(__name__)

class LamaInpainter(IInpainter):
    """Singleton facade for LaMa inpainting operations."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            logger.info("Loading LaMa model into memory...")
            print("Loading LaMa model into memory...")
            cls._instance.lama = SimpleLama()
            logger.info("LaMa model loaded successfully")
        return cls._instance

    def inpaint(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """
        Inpaint an image given a mask using the SimpleLama model.
        Accepts and returns numpy arrays (cv2 compatible).
        """
        logger.info("Starting inpainting process...")
        print("Starting inpainting process...")

        if mask.ndim == 3:
            mask = mask[:, :, 0]
        if mask.shape[:2] != image.shape[:2]:
            mask = cv2.resize(mask, (image.shape[1], image.shape[0]), interpolation=cv2.INTER_NEAREST)
            thresh = 0.5 if mask.max() <= 1.0 else 127
            mask = (mask > thresh).astype(np.uint8) * 255
        
        # 0. So LaMa is not conditioned on the removed object's pixels (avoids ghost where it obstructed another object),
        #    fill the mask region with the mean color of the mask boundary only. Mask size and shape are unchanged.
        mask_uint = (mask * 255).astype(np.uint8) if mask.max() <= 1 else mask.astype(np.uint8)
        mask_bool = mask_uint > 127
        if mask_bool.any():
            kernel = np.ones((3, 3), np.uint8)
            boundary = (cv2.dilate(mask_uint, kernel) > 0) & (~mask_bool)
            if boundary.any():
                if len(image.shape) == 3:
                    fill = np.round(image[boundary].mean(axis=0)).astype(image.dtype)
                else:
                    fill = np.round(image[boundary].mean()).astype(image.dtype)
                image = image.copy()
                image[mask_bool] = fill
        
        # 1. Convert BGR (cv2) to RGB for SimpleLama, then to PIL
        if len(image.shape) == 3 and image.shape[2] == 3:
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        else:
            image_rgb = image
        image_pil = Image.fromarray(image_rgb)
        
        # Make sure mask uses 0-255 range and convert to grayscale ('L') for LaMa.
        if mask.max() <= 1.0:
            logger.debug("Scaling mask from 0-1 to 0-255")
            mask = (mask * 255).astype(np.uint8)
        mask_pil = Image.fromarray(mask).convert('L')
        
        # 2. Run LaMa inpainting model.
        logger.debug("Running LaMa inpainting model")
        result_pil = self.lama(image_pil, mask_pil)
        logger.info("LaMa inpainting completed successfully")
        
        # 3. Convert result back to BGR so pipeline (SD, saving) stays cv2-compatible
        result_rgb = np.array(result_pil)
        if result_rgb.dtype == np.float32 or result_rgb.dtype == np.float64:
            if result_rgb.max() <= 1.0:
                result_rgb = (np.clip(result_rgb, 0, 1) * 255).astype(np.uint8)
        if len(result_rgb.shape) == 3 and result_rgb.shape[2] == 3:
            result_np = cv2.cvtColor(result_rgb, cv2.COLOR_RGB2BGR)
        else:
            result_np = result_rgb
        return result_np
