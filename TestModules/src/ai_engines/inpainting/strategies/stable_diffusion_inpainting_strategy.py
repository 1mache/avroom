from __future__ import annotations

import functools
import logging
from typing import Any

import cv2
import numpy as np
from PIL import Image

from ..image_inpainting_strategy import ImageInpaintingStrategy

logger = logging.getLogger(__name__)


_DEFAULT_MODEL_ID = "runwayml/stable-diffusion-inpainting"
_DEFAULT_PROMPT = "seamless plain flat background texture, photorealistic background, empty space"
_DEFAULT_NEGATIVE_PROMPT = (
    "furniture, table, couch, chair, sofa, ottoman, pouf, stool, vase, plant, "
    "object, item, thing, decor, shadow, 3d, person, animal, clutter, "
    "artifact, pedestal, box, blurry, smeared, ghost"
)


@functools.lru_cache(maxsize=1)
def _load_stable_diffusion_pipe(model_id: str, device: str) -> Any:
    """Load and cache a single Stable Diffusion inpainting pipeline.

    Replaces the per-instance ``__init__`` model load in the legacy
    ``StableDiffusionInpainter``.
    """
    import torch
    from diffusers import StableDiffusionInpaintPipeline

    logger.info(
        f"Loading Stable Diffusion Inpainting model on {device} "
        f"(this might take a while on first run)"
    )
    pipe = StableDiffusionInpaintPipeline.from_pretrained(
        model_id,
        torch_dtype=torch.float16 if device == "cuda" else torch.float32,
    )
    pipe = pipe.to(device)
    if device == "cuda":
        pipe.enable_attention_slicing()
    logger.info("Stable Diffusion Inpainting model loaded successfully.")
    return pipe


class StableDiffusionInpaintingStrategy(ImageInpaintingStrategy):
    """Generative inpainting strategy backed by Stable Diffusion.

    Higher fidelity but slower and more prone to hallucinating new objects
    than LaMa - the pipeline tames this by combining LaMa+SD with a low
    SD ``strength`` (see :class:`HybridInpaintingStrategy`).
    """

    DEFAULT_MODEL_ID: str = _DEFAULT_MODEL_ID
    DEFAULT_PROMPT: str = _DEFAULT_PROMPT
    DEFAULT_NEGATIVE_PROMPT: str = _DEFAULT_NEGATIVE_PROMPT

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        device: str | None = None,
        prompt: str | None = None,
        negative_prompt: str | None = None,
    ) -> None:
        self._model_id = model_id
        self._device = device or self._auto_device()
        self._prompt = prompt or self.DEFAULT_PROMPT
        self._negative_prompt = negative_prompt or self.DEFAULT_NEGATIVE_PROMPT
        logger.info(
            f"StableDiffusionInpaintingStrategy created (model={model_id}, device={self._device})"
        )

    @staticmethod
    def _auto_device() -> str:
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except ModuleNotFoundError:
            return "cpu"

    def inpaint(
        self,
        image: np.ndarray,
        mask: np.ndarray,
        prompt: str | None = None,
        strength: float = 0.35,
        **kwargs: Any,
    ) -> np.ndarray:
        logger.info("Starting Stable Diffusion inpainting process...")

        img_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(img_rgb)

        # Hard-binarize the mask so SD sees crisp boundaries.
        mask_uint8 = (mask * 255).astype(np.uint8) if mask.max() <= 1 else mask.astype(np.uint8)
        mask_binary = (mask_uint8 > 127).astype(np.uint8) * 255
        pil_mask = Image.fromarray(mask_binary).convert("L")

        original_size = pil_image.size
        pil_image_resized = pil_image.resize((512, 512))
        pil_mask_resized = pil_mask.resize((512, 512), Image.NEAREST)

        if prompt is None:
            prompt = self._prompt

        logger.info(f"Running inference with prompt: '{prompt}'")
        pipe = _load_stable_diffusion_pipe(self._model_id, self._device)
        result = pipe(
            prompt=prompt,
            negative_prompt=self._negative_prompt,
            image=pil_image_resized,
            mask_image=pil_mask_resized,
            num_inference_steps=30,
            guidance_scale=10.0,
            strength=strength,
        ).images[0]

        result = result.resize(original_size, Image.LANCZOS)
        result_cv2 = cv2.cvtColor(np.array(result), cv2.COLOR_RGB2BGR)
        logger.info("Stable Diffusion inpainting completed.")

        return result_cv2
