from pathlib import Path
import logging
import numpy as np
from PIL import Image
from PIL.Image import Image as PILImage

# Configure logging
logger = logging.getLogger(__name__)


class ImageAdapterFactory:
    """Singleton factory to create images compatible with LamaInpainterFacade and SamFacade"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ImageAdapterFactory, cls).__new__(cls)
            logger.info("ImageAdapterFactory initialized")
        return cls._instance
    
    def create_image(self, source: str | Path | PILImage) -> np.ndarray:
        """
        Load and convert image from a file path or PIL Image to a numpy array
        acceptable by LamaInpainterFacade and SamFacade.
        
        Args:
            source: Either a filesystem path to the image file or a
                ``PIL.Image.Image`` instance.
        
        Returns:
            np.ndarray: Image as numpy array in RGB format
        """
        logger.debug(f"Creating image from source: {source}")
        # If a PIL image was supplied directly, skip file handling
        if isinstance(source, PILImage):
            logger.debug("Source is already a PIL Image")
            image = source
        else:
            image_path = Path(source)
            logger.debug(f"Loading image from path: {image_path}")
            if not image_path.exists():
                logger.error(f"Image not found: {image_path}")
                raise FileNotFoundError(f"Image not found: {image_path}")
            image = Image.open(image_path)
            logger.debug(f"Image loaded: {image.size} {image.mode}")
        
        # Convert to RGB if necessary
        if image.mode != 'RGB':
            logger.debug(f"Converting image from {image.mode} to RGB")
            image = image.convert('RGB')
        
        # Convert to numpy array
        image_array = np.array(image)
        logger.debug(f"Image converted to numpy array: {image_array.shape}")
        
        return image_array


def get_image_adapter_factory() -> ImageAdapterFactory:
    """Get singleton instance of ImageAdapterFactory"""
    return ImageAdapterFactory()