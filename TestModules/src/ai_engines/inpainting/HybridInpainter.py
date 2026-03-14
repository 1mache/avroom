import numpy as np
import logging
import cv2  # Required for debugging
import os   # Required for debugging
from core.interfaces import IInpainter
from ai_engines.inpainting.LamaInpainter import LamaInpainter
from ai_engines.inpainting.StableDiffusionInpainter import StableDiffusionInpainter

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
        lama_result = self.lama.inpaint(image, mask)

        # ==========================================
        # DEBUG: Save LaMa output to disk
        # ==========================================
        debug_dir = os.path.join(os.path.dirname(__file__), "..", "outputs")
        os.makedirs(debug_dir, exist_ok=True)
        debug_path = os.path.join(debug_dir, "debug_lama_output.png")
        cv2.imwrite(debug_path, lama_result)
        logger.info(f"Saved intermediate LaMa result to {debug_path} for debugging.")
        # ==========================================

        logger.info("--- Hybrid Pipeline Phase 2: Texture refinement (SD) ---")
        sd_kwargs = kwargs.copy()
        
        # 1. Apply dynamic strength provided by the router (fallback to 0.55)
        dynamic_strength = kwargs.get('strength', 0.55)
        sd_kwargs['strength'] = dynamic_strength
        logger.info(f"Using dynamic SD strength: {dynamic_strength}")
        
        # 2. Inject an adaptive prompt suitable for textures instead of flat walls
        if 'prompt' not in sd_kwargs:
            sd_kwargs['prompt'] = "seamless continuation of the surrounding textures, photorealistic interior design, extremely high detail"

        # Execute Stable Diffusion with dynamic parameters
        final_result = self.sd.inpaint(lama_result, mask, **sd_kwargs)
        
        logger.info("Hybrid Pipeline completed successfully.")
        return final_result