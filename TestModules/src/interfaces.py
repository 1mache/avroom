from abc import ABC, abstractmethod
import numpy as np

class IDepthFacade(ABC):
    """Interface for depth map generation facades."""
    @abstractmethod
    def get_optimized_depth_map(self, image: np.ndarray) -> np.ndarray:
        pass

class IImageAdapter(ABC):
    """Interface for adapting raw image data into specific formats."""
    @abstractmethod
    def get_adapted_image(self, raw_data: any, image_id: str, point: tuple) -> np.ndarray:
        pass