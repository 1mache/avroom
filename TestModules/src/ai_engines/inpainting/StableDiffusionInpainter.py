import torch
import numpy as np
import logging
from PIL import Image
import cv2
from diffusers import StableDiffusionInpaintPipeline
from ...core.interfaces import IInpainter

logger = logging.getLogger(__name__)

class StableDiffusionInpainter(IInpainter):
    """
    Inpainting engine using Stable Diffusion.
    Provides photo-realistic generation for removed objects.
    """
    def __init__(self, model_id="runwayml/stable-diffusion-inpainting"):
        # Auto-detect hardware target (CPU or CUDA GPU).
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Loading Stable Diffusion Inpainting model on {self.device} (This might take a while on first run...)")
        
        # Load model weights from HuggingFace.
        self.pipe = StableDiffusionInpaintPipeline.from_pretrained(
            model_id,
            # Use float16 on GPU for lower memory use, float32 on CPU for compatibility.
            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
        )
        self.pipe = self.pipe.to(self.device)
        
        # Extra memory optimization for GPU runs.
        if self.device == "cuda":
            self.pipe.enable_attention_slicing()

        # Minimal prompt — empty space only (good-run wording; "sharp/detailed" can encourage structure/objects)
        self.SD_prompt = "seamless plain flat background texture, photorealistic background, empty space"
        self.SD_negative_prompt = "furniture, table, couch, chair, sofa, ottoman, pouf, stool, vase, plant, object, item, thing, decor, shadow, 3d, person, animal, clutter, artifact, pedestal, box, blurry, smeared, ghost"
            
        logger.info("Stable Diffusion Inpainting model loaded successfully.")

    def inpaint(self, image: np.ndarray, mask: np.ndarray, 
                prompt: str = None, 
                strength: float = 0.35) -> np.ndarray:
        """
        Inpaints the masked area using generative AI.
        """
        logger.info("Starting Stable Diffusion inpainting process...")
        
        img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(img_rgb)
        
        # Keep mask strictly binary so SD gets a hard edge (avoids smeared corners at boundary)
        mask_uint8 = (mask * 255).astype(np.uint8) if mask.max() <= 1 else mask.astype(np.uint8)
        mask_binary = ((mask_uint8 > 127).astype(np.uint8) * 255)
        pil_mask = Image.fromarray(mask_binary).convert("L")
        
        original_size = pil_image.size
        pil_image_resized = pil_image.resize((512, 512))
        pil_mask_resized = pil_mask.resize((512, 512), Image.NEAREST)

        if prompt is None:
            prompt = self.SD_prompt
            logger.debug("No prompt provided, using default prompt.")
            
        logger.info(f"Running inference with prompt: '{prompt}'")
        
        result = self.pipe(
            prompt=prompt, 
            negative_prompt=self.SD_negative_prompt,
            image=pil_image_resized,
            mask_image=pil_mask_resized,
            num_inference_steps=30,
            guidance_scale=10.0,
            strength=strength
        ).images[0]
        
        result = result.resize(original_size, Image.LANCZOS)
        result_cv2 = cv2.cvtColor(np.array(result), cv2.COLOR_RGB2BGR)
        logger.info("Stable Diffusion inpainting completed.")
        
        return result_cv2
