from pathlib import Path
from typing import Union
import numpy as np
from PIL import Image
from PIL.Image import Image as PILImage


class ImageAdapterFactory:
    """Singleton factory to create images compatible with LamaInpainterFacade and SamFacade"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ImageAdapterFactory, cls).__new__(cls)
        return cls._instance
    
    def create_image(self, source: Union[str, Path, PILImage]) -> np.ndarray:
        """
        Load and convert image from a file path or PIL Image to a numpy array
        acceptable by LamaInpainterFacade and SamFacade.
        
        Args:
            source: Either a filesystem path to the image file or a
                ``PIL.Image.Image`` instance.
        
        Returns:
            np.ndarray: Image as numpy array in RGB format
        """
        # If a PIL image was supplied directly, skip file handling
        if isinstance(source, PILImage):
            image = source
        else:
            image_path = Path(source)
            if not image_path.exists():
                raise FileNotFoundError(f"Image not found: {image_path}")
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