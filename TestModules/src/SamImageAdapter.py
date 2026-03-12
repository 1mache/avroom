import cv2
import logging
import numpy as np
from interfaces import IImageAdapter

# Configure logging
logger = logging.getLogger(__name__)

class CacheComponent:
    """A separate caching component to be used via composition."""
    def __init__(self):
        self._cache_key = None
        self._cached_data = None
        logger.debug("CacheComponent initialized")

    def get(self, key: str):
        if self._cache_key == key:
            return self._cached_data
        return None

    def set(self, key: str, data: any):
        self._cache_key = key
        self._cached_data = data


class SamImageAdapter(IImageAdapter):
    """
    Adapter to convert raw depth maps into SAM-compatible RGB numpy arrays.
    Uses Composition to implement caching.
    """
    def __init__(self):
        # COMPOSITION: The Adapter 'has a' CacheComponent
        self._cache = CacheComponent()
        logger.info("SamImageAdapter initialized")

    def get_adapted_image(self, raw_data: any, image_id: str, point: tuple) -> np.ndarray:
        # Create a unique key based on both the image identity and the clicked point
        cache_key = f"{image_id}_{point[0]}_{point[1]}"
        
        # Check cache first
        cached_image = self._cache.get(cache_key)
        if cached_image is not None:
            logger.info("Using cached adapted image")
            print("[Adapter] Using CACHED adapted image.")
            return cached_image

        logger.info("Adapting new data for SAM and caching it...")
        print("[Adapter] Adapting new data for SAM and caching it...")
        
        # Adaptation Logic: Convert to Numpy
        adapted = np.array(raw_data)
        
        # SAM requires 3 channels (RGB). If depth map is 1 channel (Grayscale), convert it.
        if len(adapted.shape) == 2:
            logger.debug("Converting grayscale depth to RGB")
            adapted = cv2.cvtColor(adapted, cv2.COLOR_GRAY2RGB)
        elif len(adapted.shape) == 3 and adapted.shape[2] == 4:
            logger.debug("Converting RGBA to RGB")
            adapted = cv2.cvtColor(adapted, cv2.COLOR_RGBA2RGB)
            
        # Save to cache using the composed component
        self._cache.set(cache_key, adapted)
        logger.debug(f"Adapted image cached with key: {cache_key}")
        
        return adapted