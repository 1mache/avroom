import numpy as np
import logging
import cv2
from core.interfaces import IInpainter
from utils.DebugImageSaver import DebugImageSaver
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
        self.image_saver = DebugImageSaver()
        
        logger.info("Hybrid Pipeline initialized successfully.")

    def inpaint(self, image: np.ndarray, mask: np.ndarray, **kwargs) -> np.ndarray:
        # Ensure mask is same size as image (depth/SAM can sometimes differ)
        if mask.shape[:2] != image.shape[:2]:
            mask = cv2.resize(mask, (image.shape[1], image.shape[0]), interpolation=cv2.INTER_NEAREST)
            thresh = 0.5 if mask.max() <= 1.0 else 127
            mask = (mask > thresh).astype(np.uint8) * 255
        logger.info("--- Hybrid Pipeline Phase 1: Structural removal (LaMa) ---")
        lama_result = self.lama.inpaint(image, mask)

        # DEBUG: Save LaMa intermediate result
        self.image_saver.save("debug_lama_output", lama_result)

        logger.info("--- Hybrid Pipeline Phase 2: Texture refinement (SD) ---")
        sd_kwargs = kwargs.copy()
        
        # 1. Apply dynamic strength (low = no hallucination; SD runs at 512px so higher strength tends to add objects)
        dynamic_strength = kwargs.get('strength', 0.35)
        sd_kwargs['strength'] = dynamic_strength
        logger.info(f"Using dynamic SD strength: {dynamic_strength}")
        # Do not override prompt — use SD inpainter's default (empty floor/carpet, no objects)

        # 2. Skip SD when strength is very low (LaMa-only path: no smear from SD resize, no object hallucination)
        if dynamic_strength <= 0.2:
            final_result = lama_result.copy()
            logger.info("Skipping SD (strength <= 0.2); using LaMa result only.")
        else:
            final_result = self.sd.inpaint(lama_result, mask, **sd_kwargs)

        # 3. Sharpen: stronger so inpainted area and reimagined edges match surroundings
        sigma = 0.8
        blurred = cv2.GaussianBlur(final_result, (0, 0), sigma)
        f = final_result.astype(np.float32)
        final_result = np.clip(f + 0.6 * (f - blurred.astype(np.float32)), 0, 255).astype(np.uint8)

        # 4. Nudge color toward background only in mask interior (not the boundary band)
        #    so reimagined edges of obstructed objects keep their shape and are not distorted
        mask_bool = (mask > 127) if (mask.dtype == np.uint8 or mask.max() > 1) else (mask > 0.5)
        if mask_bool.any() and len(final_result.shape) == 3:
            mask_uint = (mask * 255).astype(np.uint8) if mask.max() <= 1 else mask.astype(np.uint8)
            kernel = np.ones((3, 3), np.uint8)
            boundary = (cv2.dilate(mask_uint, kernel) > 0) & (~mask_bool)
            # Erode mask so we only adjust interior (background) pixels, not the reimagined edge band
            interior_only = cv2.erode(mask_uint, np.ones((7, 7), np.uint8)) > 127
            if boundary.any() and interior_only.any():
                boundary_mean = final_result[boundary].mean(axis=0)
                inside_mean = final_result[interior_only].mean(axis=0)
                shift = (boundary_mean.astype(np.float32) - inside_mean.astype(np.float32)) * 0.35
                out = final_result.astype(np.float32)
                out[interior_only] = np.clip(out[interior_only] + shift, 0, 255)
                final_result = out.astype(np.uint8)
        # (Removed extra mask-only sharpen — it made reimagined edges look weird and not match object shape)

        # DEBUG: Save Stable Diffusion intermediate/final result
        self.image_saver.save("debug_sd_output", final_result)

        logger.info("Hybrid Pipeline completed successfully.")
        return final_result