from __future__ import annotations

import functools
import logging
from typing import Any

import cv2
import numpy as np
from PIL import Image

from ...inpainting_verification.crop import crop_with_window, mask_crop_window
from ..image_inpainting_strategy import ImageInpaintingStrategy

logger = logging.getLogger(__name__)


_DEFAULT_MODEL_ID = "runwayml/stable-diffusion-inpainting"
_DEFAULT_PROMPT = "seamless plain flat background texture, photorealistic background, empty space"
_DEFAULT_NEGATIVE_PROMPT = (
    "furniture, table, couch, chair, sofa, ottoman, pouf, stool, vase, plant, "
    "object, item, thing, decor, shadow, 3d, person, animal, clutter, "
    "artifact, pedestal, box, blurry, smeared, ghost"
)

# SD 1.5 was trained at 512px; this is the minimum crop context even for tiny masks.
SD_MIN_CROP_PX: int = 512
# Match Gemini's pad ratio so SD and the verifier reason about the same window.
SD_CROP_PAD_RATIO: float = 0.35
# ponytail: OOM guard only — never engages at typical 528x734 windows.
# Upgrade path: bump or remove when running on 24+ GB VRAM.
SD_MAX_GEN_SIDE: int = 1024


def _snap_to_multiple_of_8(
    width: int, height: int, max_side: int = SD_MAX_GEN_SIDE
) -> tuple[int, int]:
    """Round dims to the VAE's /8 grid, capped for OOM safety.

    Snaps each dimension independently (no aspect-ratio distortion beyond one
    grid step). Scales both dims down proportionally when the long side would
    exceed ``max_side`` after snapping.
    """
    w = max(8, (width + 7) // 8 * 8)
    h = max(8, (height + 7) // 8 * 8)
    long_side = max(w, h)
    if long_side > max_side:
        scale = max_side / long_side
        w = max(8, int(w * scale) // 8 * 8)
        h = max(8, int(h * scale) // 8 * 8)
    return w, h


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
        """Inpaint the masked region and return a full-frame BGR array.

        SD runs on a native-resolution crop around the mask rather than the
        squashed full frame, preventing the 3x upscale smear and paste seam.
        Only pixels inside the mask are written back; surrounding pixels are
        byte-identical to ``image`` so Gemini's dual-crop verification sees
        an uncorrupted reference on both sides of the outline.
        """
        logger.info("Starting Stable Diffusion inpainting process...")

        # Hard-binarize before computing the crop window.
        mask_uint8 = (mask * 255).astype(np.uint8) if mask.max() <= 1 else mask.astype(np.uint8)
        if mask_uint8.ndim == 3:
            mask_uint8 = mask_uint8[:, :, 0]
        mask_binary = (mask_uint8 > 127).astype(np.uint8) * 255

        window = mask_crop_window(
            mask_binary,
            pad_ratio=SD_CROP_PAD_RATIO,
            min_side_px=SD_MIN_CROP_PX,
            min_side_frac=0.0,
        )

        crop_bgr = crop_with_window(image, window)
        crop_mask = crop_with_window(mask_binary, window)

        gen_w, gen_h = _snap_to_multiple_of_8(window.width, window.height)

        crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(crop_rgb).resize((gen_w, gen_h), Image.LANCZOS)
        pil_mask = Image.fromarray(crop_mask).convert("L").resize(
            (gen_w, gen_h), Image.NEAREST
        )

        if prompt is None:
            prompt = self._prompt
        negative_prompt = str(kwargs.get("negative_prompt", self._negative_prompt))
        num_inference_steps = int(kwargs.get("num_inference_steps", 30))
        guidance_scale = float(kwargs.get("guidance_scale", 10.0))

        logger.info(
            "SD inference: strength=%s steps=%s guidance=%s gen_size=%dx%d "
            "window=(%d,%d)-(%d,%d) prompt=%r negative=%r",
            strength,
            num_inference_steps,
            guidance_scale,
            gen_w,
            gen_h,
            window.y0,
            window.y1,
            window.x0,
            window.x1,
            prompt,
            negative_prompt,
        )
        pipe = _load_stable_diffusion_pipe(self._model_id, self._device)
        result_pil = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            image=pil_image,
            mask_image=pil_mask,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            strength=strength,
        ).images[0]

        # Resize back to the window's native dimensions before pasting.
        if result_pil.size != (window.width, window.height):
            result_pil = result_pil.resize((window.width, window.height), Image.LANCZOS)

        result_crop_bgr = cv2.cvtColor(np.array(result_pil), cv2.COLOR_RGB2BGR)

        # Paste only the mask pixels; all surroundings stay byte-identical.
        out = image.copy()
        crop_mask_bool = crop_mask > 127
        out_crop = out[window.y0 : window.y1, window.x0 : window.x1]
        out_crop[crop_mask_bool] = result_crop_bgr[crop_mask_bool]

        logger.info("Stable Diffusion inpainting completed.")
        return out
