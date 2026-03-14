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

class IInpainter(ABC):
    """
    Interface for all inpainting engines (LaMa, Stable Diffusion, Hybrid, etc.).
    Ensures that any inpainting class implements the inpaint method.
    """
    @abstractmethod
    def inpaint(self, image: np.ndarray, mask: np.ndarray, **kwargs) -> np.ndarray:
        """
        Executes the inpainting process on the provided image using the mask.
        
        Args:
            image (np.ndarray): The source image in BGR format.
            mask (np.ndarray): The binary or boolean mask indicating the area to remove.
            **kwargs: Additional model-specific parameters (e.g., prompt, strength).
            
        Returns:
            np.ndarray: The resulting inpainted image in BGR format.
        """
        pass


class ISegmentationRoutingStrategy(ABC):
    @abstractmethod
    def choose_input(self, rgb_image: np.ndarray, raw_depth: np.ndarray, adapted_depth: np.ndarray, x: int, y: int) -> np.ndarray:
        pass