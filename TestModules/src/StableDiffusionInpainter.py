import torch
import numpy as np
import logging
from PIL import Image
import cv2
from diffusers import StableDiffusionInpaintPipeline

logger = logging.getLogger(__name__)

class StableDiffusionInpainter:
    """
    Inpainting engine using Stable Diffusion.
    Provides photo-realistic generation for removed objects.
    """
    def __init__(self, model_id="runwayml/stable-diffusion-inpainting"):
        # זיהוי אוטומטי של חומרה (CPU או כרטיס מסך CUDA)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Loading Stable Diffusion Inpainting model on {self.device} (This might take a while on first run...)")
        
        # טעינת המודל מ-HuggingFace
        self.pipe = StableDiffusionInpaintPipeline.from_pretrained(
            model_id,
            # שימוש ב-float16 לכרטיסי מסך (חיסכון בזיכרון), ו-float32 ל-CPU
            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
        )
        self.pipe = self.pipe.to(self.device)
        
        # אופטימיזציה לחיסכון בזיכרון אם יש כרטיס מסך
        if self.device == "cuda":
            self.pipe.enable_attention_slicing()

        self.SD_prompt = "seamless plain flat background texture, photorealistic background, empty space"
        self.SD_negative_prompt = "table, furniture, object, pouf, shadow, 3d, person, animal, cat, dog, clutter, artifact, pedestal, box"
            
        logger.info("Stable Diffusion Inpainting model loaded successfully.")

    def inpaint(self, image: np.ndarray, mask: np.ndarray, 
                # שינוי 1: תיאור מדויק רק של הטקסטורה הרצויה
                prompt: str = None) -> np.ndarray:
        """
        Inpaints the masked area using generative AI.
        """
        logger.info("Starting Stable Diffusion inpainting process...")
        
        img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(img_rgb)
        
        mask_uint8 = (mask * 255).astype(np.uint8)
        pil_mask = Image.fromarray(mask_uint8).convert("L")
        
        original_size = pil_image.size
        pil_image_resized = pil_image.resize((512, 512))
        pil_mask_resized = pil_mask.resize((512, 512))

        if prompt is None:
            prompt = self.SD_prompt
            logger.debug("No prompt provided, using default prompt.")
            
        logger.info(f"Running inference with prompt: '{prompt}'")
        
        result = self.pipe(
            prompt=prompt, # כאן תיקנתי באג קטן שהיה בקוד שלך (קראת ל-self.SD_prompt במקום ל-prompt שנכנס)
            negative_prompt=self.SD_negative_prompt,
            image=pil_image_resized,
            mask_image=pil_mask_resized,
            num_inference_steps=20,
            guidance_scale=8.5,
            # הוספנו את פרמטר הכוח! 1.0 אומר - התעלם לגמרי מהפיקסלים המקוריים שמתחת למסכה
            strength=1.0 
        ).images[0]
        
        result = result.resize(original_size, Image.LANCZOS)
        result_cv2 = cv2.cvtColor(np.array(result), cv2.COLOR_RGB2BGR)
        logger.info("Stable Diffusion inpainting completed.")
        
        return result_cv2