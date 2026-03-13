import numpy as np
import logging
from PIL import Image
from simple_lama_inpainting import SimpleLama
from interfaces import IInpainter

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
        
        # 1. המרה מ-NumPy ל-PIL Image
        # ההנחה היא שהתמונה כבר בפורמט RGB (אם עשית cvtColor לפני כן)
        image_pil = Image.fromarray(image)
        
        # וידוא שהמסכה בטווח הנכון (0-255) והמרה למצב Grayscale ('L')
        if mask.max() <= 1.0:
            logger.debug("Scaling mask from 0-1 to 0-255")
            mask = (mask * 255).astype(np.uint8)
        mask_pil = Image.fromarray(mask).convert('L')
        
        # 2. הפעלת מודל LaMa
        logger.debug("Running LaMa inpainting model")
        result_pil = self.lama(image_pil, mask_pil)
        logger.info("LaMa inpainting completed successfully")
        
        # 3. המרה חזרה ל-NumPy כדי שיתאים לשאר הקוד שלך
        result_np = np.array(result_pil)
        
        return result_np