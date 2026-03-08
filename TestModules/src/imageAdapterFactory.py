from pathlib import Path
from typing import Union
import numpy as np
from PIL import Image


class ImageAdapterFactory:
    """Singleton factory to create images compatible with LamaInpainterFacade and SamFacade"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ImageAdapterFactory, cls).__new__(cls)
        return cls._instance
    
    def create_image(self, path: Union[str, Path]) -> np.ndarray:
        """
        Load and convert image from path to format acceptable by LamaInpainterFacade and SamFacade
        
        Args:
            path: Path to the image file
            
        Returns:
            np.ndarray: Image as numpy array in RGB format
        """
        image_path = Path(path)
        
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        
        # Load image with PIL
        image = Image.open(image_path)
        
        # Convert to RGB if necessary
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Convert to numpy array
        image_array = np.array(image)
        
        return image_array


def get_image_adapter_factory() -> ImageAdapterFactory:
    """Get singleton instance of ImageAdapterFactory"""
    return ImageAdapterFactory()