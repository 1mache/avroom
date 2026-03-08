import numpy as np
from PIL import Image
from simple_lama_inpainting import SimpleLama

class LamaFacade:
    """Singleton facade for LaMa inpainting operations."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            print("Loading LaMa model into memory...")
            cls._instance.lama = SimpleLama()
        return cls._instance

    def inpaint(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """
        Inpaint an image given a mask using the SimpleLama model.
        Accepts and returns numpy arrays (cv2 compatible).
        """
        print("Starting inpainting process...")
        
        # 1. המרה מ-NumPy ל-PIL Image
        # ההנחה היא שהתמונה כבר בפורמט RGB (אם עשית cvtColor לפני כן)
        image_pil = Image.fromarray(image)
        
        # וידוא שהמסכה בטווח הנכון (0-255) והמרה למצב Grayscale ('L')
        if mask.max() <= 1.0:
            mask = (mask * 255).astype(np.uint8)
        mask_pil = Image.fromarray(mask).convert('L')
        
        # 2. הפעלת מודל LaMa
        result_pil = self.lama(image_pil, mask_pil)
        
        # 3. המרה חזרה ל-NumPy כדי שיתאים לשאר הקוד שלך
        result_np = np.array(result_pil)
        
        return result_np