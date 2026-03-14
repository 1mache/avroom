import os
import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)

class DebugImageSaver:
    """
    A centralized utility for saving debug and intermediate images.
    Abstracts away file path resolutions and directory management.
    """
    def __init__(self, output_folder_name: str = "outputs"):
        # Calculate project root dynamically (assuming file is in src/utils/)
        # This goes up two levels: utils -> src -> TestModules
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
        self.output_dir = os.path.join(self.project_root, output_folder_name)
        
        # Ensure the outputs directory exists
        os.makedirs(self.output_dir, exist_ok=True)
        logger.info(f"DebugImageSaver initialized. Saving to: {self.output_dir}")

    def save(self, filename: str, image: np.ndarray) -> str:
        """
        Saves a numpy array (OpenCV image) to the configured outputs directory.
        Automatically handles boolean masks and appends .png if needed.
        """
        if image is None or not isinstance(image, np.ndarray):
            logger.warning(f"Cannot save {filename}: invalid image data.")
            return ""

        # === התיקון הקריטי למסכות של SAM ===
        # אם התמונה היא בוליאנית (True/False), נמיר אותה לשחור-לבן (0/255)
        save_image = image
        if save_image.dtype == bool:
            save_image = (save_image * 255).astype(np.uint8)

        if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            filename += '.png'
            
        filepath = os.path.join(self.output_dir, filename)
        
        try:
            cv2.imwrite(filepath, save_image)
            logger.debug(f"[DEBUG SAVER] Image saved successfully: {filename}")
            return filepath
        except Exception as e:
            logger.error(f"[DEBUG SAVER] Failed to save {filename}: {e}")
            return ""