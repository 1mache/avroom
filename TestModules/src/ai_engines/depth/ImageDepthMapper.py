import logging
import numpy as np
from PIL import Image
from transformers import pipeline
from typing import Optional

# Configure logging
logger = logging.getLogger(__name__)

class ImageDepthMapper:
    """Singleton facade for depth mapping using HuggingFace depth-anything models.

    Allows the model and task used by the underlying pipeline to be changed via
    properties.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ImageDepthMapper, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # default pipeline parameters
        self._model_name = "LiheYoung/depth-anything-small-hf"
        self._task = "depth-estimation"
        self._create_pipeline()
        self._initialized = True
        logger.info(f"ImageDepthMapper initialized with model={self._model_name}")

    # internal helper used when model or task changes
    def _create_pipeline(self) -> None:
        """(Re)build the underlying HuggingFace pipeline using current settings."""
        logger.info(f"Creating pipeline with model={self._model_name}, task={self._task}")
        self.depth_pipeline = pipeline(
            task=self._task,
            model=self._model_name
        )
        logger.debug("Pipeline created successfully")

    @property
    def model(self) -> str:
        """The name of the HF model used by the depth pipeline."""
        return self._model_name

    @model.setter
    def model(self, new_model: str) -> None:
        """Change the model and rebuild the pipeline if different."""
        if new_model != self._model_name:
            logger.info(f"Switching model from {self._model_name} to {new_model}")
            self._model_name = new_model
            self._create_pipeline()

    @property
    def task(self) -> str:
        """The task name passed to :func:`transformers.pipeline`."""
        return self._task

    @task.setter
    def task(self, new_task: str) -> None:
        """Change the pipeline task and rebuild if different."""
        if new_task != self._task:
            logger.info(f"Switching task from {self._task} to {new_task}")
            self._task = new_task
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
        logger.debug("Computing depth map...")
        # Convert numpy array to PIL Image if needed
        if isinstance(image, np.ndarray):
            pil_image = Image.fromarray(image.astype('uint8'))
        else:
            pil_image = image
        
        # Calculate depth map
        depth_result = self.depth_pipeline(pil_image)
        depth_image = depth_result['depth']
        logger.debug("Depth map computed")
        
        # Save if output path provided
        if output_path:
            depth_image.save(output_path)
            logger.debug(f"Depth map saved to {output_path}")
        
        return depth_image