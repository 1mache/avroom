import numpy as np
from PIL import Image
from transformers import pipeline
from typing import Optional

class ImageDepthMapper:
    """Singleton facade for depth mapping using HuggingFace depth-anything-small-hf model."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ImageDepthMapper, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._model_name = "LiheYoung/depth-anything-small-hf"
        self._create_pipeline()
        self._initialized = True

    # internal helper used when the model name changes
    def _create_pipeline(self) -> None:
        """(Re)build the underlying HuggingFace pipeline using ``self._model_name``."""
        self.depth_pipeline = pipeline(
            task="depth-estimation",
            model=self._model_name
        )

    @property
    def model(self) -> str:
        """The name of the HF model used by the depth pipeline."""
        return self._model_name

    @model.setter
    def model(self, new_model: str) -> None:
        """Change the model and rebuild the pipeline if different."""
        if new_model != self._model_name:
            self._model_name = new_model
            self._create_pipeline()
    
    def get_depth_map(
        self,
        image: np.ndarray,
        output_path: Optional[str] = None
    ) -> Image.Image:
        """
        Generate depth map from image array.
        
        Args:
            image: Input image as numpy array
            output_path: Optional path to save the depth map image
            
        Returns:
            PIL Image containing the depth map
        """
        # Convert numpy array to PIL Image if needed
        if isinstance(image, np.ndarray):
            pil_image = Image.fromarray(image.astype('uint8'))
        else:
            pil_image = image
        
        # Calculate depth map
        depth_result = self.depth_pipeline(pil_image)
        depth_image = depth_result['depth']
        
        # Save if output path provided
        if output_path:
            depth_image.save(output_path)
        
        return depth_image