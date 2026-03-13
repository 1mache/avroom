import numpy as np
import logging
from interfaces import IInpainter
from LamaInpainter import LamaInpainter
from StableDiffusionInpainter import StableDiffusionInpainter

logger = logging.getLogger(__name__)

class HybridInpainter(IInpainter):
    """
    A composite inpainter that chains multiple models together.
    It runs LaMa first for structural removal to prevent hallucinations, 
    followed by Stable Diffusion for texture refinement and photorealism.
    """
    def __init__(self):
        logger.info("Initializing Hybrid Inpainter Pipeline...")
        
        # Initialize both models into memory
        self.lama = LamaInpainter()
        self.sd = StableDiffusionInpainter()
        
        logger.info("Hybrid Pipeline initialized successfully.")

    def inpaint(self, image: np.ndarray, mask: np.ndarray, **kwargs) -> np.ndarray:
        logger.info("--- Hybrid Pipeline Phase 1: Structural removal (LaMa) ---")
        # LaMa processes the image and mask to completely remove the object structurally.
        # This guarantees no new objects are hallucinated, but leaves a blurry texture.
        lama_result = self.lama.inpaint(image, mask)

        logger.info("--- Hybrid Pipeline Phase 2: Texture refinement (SD) ---")
        # Copy kwargs to avoid mutating the original dictionary
        sd_kwargs = kwargs.copy()
        
        # Override the strength parameter for Stable Diffusion.
        # A low strength (0.35) forces SD to preserve the structural emptiness created by LaMa,
        # while only adding high-frequency details (like carpet fibers) to the blurry patch.
        sd_kwargs['strength'] = 0.35 
        
        # Stable Diffusion refines the blurry result from LaMa
        final_result = self.sd.inpaint(lama_result, mask, **sd_kwargs)
        
        return final_result