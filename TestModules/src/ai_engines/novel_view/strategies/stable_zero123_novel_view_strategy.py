from __future__ import annotations

import functools
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from ..novel_view_preprocess import (
    DEFAULT_MODEL_SIZE,
    composite_model_output_on_canvas,
    prepare_cutout_for_model,
    rgb_to_rgba_with_white_background,
    rgba_to_rgb_on_white,
)
from ..novel_view_strategy import NovelViewStrategy

logger = logging.getLogger(__name__)

# Diffusers-ready conversion of Stable Zero123 weights (zero123-hf author).
# Official stabilityai/stable-zero123 is ckpt-only and cannot be loaded via from_pretrained.
_DEFAULT_MODEL_ID = "kxic/stable-zero123"
_MODEL_ID_ENV = "NOVEL_VIEW_MODEL_ID"
_DEFAULT_GUIDANCE_SCALE = 3.0
_DEFAULT_INFERENCE_STEPS = 50


def _resolve_model_id(explicit: str | None = None) -> str:
    """Return the HF repo id for the Zero123 pipeline (env override supported)."""

    if explicit is not None:
        return explicit
    return os.environ.get(_MODEL_ID_ENV, _DEFAULT_MODEL_ID)


class StableZero123NovelViewError(RuntimeError):
    """Raised when Stable Zero123 novel-view inference fails."""


@functools.lru_cache(maxsize=2)
def _load_zero123_pipeline(model_id: str, device: str) -> Any:
    """Load and cache the Stable Zero123 Diffusers community pipeline.

    ``kxic/stable-zero123`` (and related Zero123 Diffusers repos) declare
    ``CCProjection`` as a custom component in ``model_index.json`` without
    shipping ``cc_projection/pipeline_zero1to3.py``. Diffusers 0.37 therefore
    cannot use ``DiffusionPipeline.from_pretrained`` directly; we assemble the
    pipeline from subfolder weights plus the community ``pipeline_zero1to3`` module.
    """

    try:
        import torch
        from diffusers import AutoencoderKL, DDIMScheduler, UNet2DConditionModel
        from diffusers.utils import get_class_from_dynamic_module
        from huggingface_hub import snapshot_download
        from transformers import CLIPImageProcessor, CLIPVisionModelWithProjection
    except ModuleNotFoundError as exc:
        logger.error("Stable Zero123 import failed: %s", exc)
        raise RuntimeError(
            "Stable Zero123 inference requires PyTorch, diffusers, and transformers. "
            "Install project dependencies: pip install -r requirements.txt"
        ) from exc

    dtype = torch.float16 if device == "cuda" else torch.float32
    logger.info("Lazy-loading Stable Zero123 from %s onto %s", model_id, device)
    try:
        pipe_cls = get_class_from_dynamic_module(
            "pipeline_zero1to3",
            module_file="pipeline_zero1to3.py",
            class_name="Zero1to3StableDiffusionPipeline",
        )
        cc_projection_cls = get_class_from_dynamic_module(
            "pipeline_zero1to3",
            module_file="pipeline_zero1to3.py",
            class_name="CCProjection",
        )

        cache_dir = snapshot_download(model_id)
        logger.debug("Zero123 weights cache dir: %s", cache_dir)

        vae = AutoencoderKL.from_pretrained(cache_dir, subfolder="vae", torch_dtype=dtype)
        unet = UNet2DConditionModel.from_pretrained(cache_dir, subfolder="unet", torch_dtype=dtype)
        scheduler = DDIMScheduler.from_pretrained(cache_dir, subfolder="scheduler")
        image_encoder = CLIPVisionModelWithProjection.from_pretrained(
            cache_dir,
            subfolder="image_encoder",
            torch_dtype=dtype,
        )
        feature_extractor = CLIPImageProcessor.from_pretrained(
            cache_dir,
            subfolder="feature_extractor",
        )

        cc_projection = cc_projection_cls()
        cc_weights_path = Path(cache_dir) / "cc_projection" / "diffusion_pytorch_model.bin"
        cc_projection.load_state_dict(
            torch.load(cc_weights_path, map_location="cpu", weights_only=True)
        )

        pipe = pipe_cls(
            vae,
            image_encoder,
            unet,
            scheduler,
            None,
            feature_extractor,
            cc_projection,
            requires_safety_checker=False,
        )
    except Exception as exc:
        logger.exception("Failed to load Zero123 pipeline from %s", model_id)
        raise StableZero123NovelViewError(
            f"Failed to load Zero123 pipeline from {model_id!r}: {exc}. "
            "The official stabilityai/stable-zero123 repo is ckpt-only (no model_index.json). "
            f"Use the default {_DEFAULT_MODEL_ID!r} or set {_MODEL_ID_ENV} to a Diffusers-formatted repo."
        ) from exc

    if "stable" in model_id.lower():
        pipe.stable_zero123 = True

    pipe = pipe.to(device)
    if device == "cuda":
        pipe.enable_attention_slicing()
    logger.info("Stable Zero123 pipeline loaded successfully")
    return pipe


class StableZero123NovelViewStrategy(NovelViewStrategy):
    """Novel-view synthesis via Stable Zero123 (Diffusers Zero1to3 pipeline).

    Accepts an object-centric RGBA cutout, preprocesses it for the model,
    and returns a full-canvas RGBA ``numpy.ndarray`` (BGRA channel order)
    suitable for PNG export and frontend compositing.

    Pose mapping follows the Zero1to3 community pipeline:
    ``[elevation_deg + relative_elevation_deg, azimuth_deg, radius]``.
    Use ``guidance_scale≈3`` — higher values over-amplify pose conditioning.
    """

    def __init__(
        self,
        model_id: str | None = None,
        *,
        device: str | None = None,
        guidance_scale: float = _DEFAULT_GUIDANCE_SCALE,
        num_inference_steps: int = _DEFAULT_INFERENCE_STEPS,
        model_size: int = DEFAULT_MODEL_SIZE,
    ) -> None:
        self._model_id = _resolve_model_id(model_id)
        self._device = device or self._auto_device()
        self._guidance_scale = guidance_scale
        self._num_inference_steps = num_inference_steps
        self._model_size = model_size
        logger.info(
            "StableZero123NovelViewStrategy created (model=%s, device=%s, cfg=%.1f)",
            self._model_id,
            self._device,
            guidance_scale,
        )

    @staticmethod
    def _auto_device() -> str:
        try:
            import torch

            return "cuda" if torch.cuda.is_available() else "cpu"
        except ModuleNotFoundError:
            return "cpu"

    def synthesize(
        self,
        image: bytes | np.ndarray | Image.Image | Path | str,
        *,
        elevation_deg: float,
        azimuth_deg: float,
        relative_elevation_deg: float = 0.0,
        radius: float = 0.0,
        seed: int = 0,
        mesh: bytes | Path | str | None = None,
    ) -> np.ndarray:
        """Run Stable Zero123 on a cutout and return a full-canvas BGRA array.

        ``mesh`` is accepted for contract parity with mesh-render strategies and
        is ignored — Zero123 is image-to-image only.
        """

        if mesh is not None:
            logger.debug("Stable Zero123 ignoring mesh=%r (image-to-image only)", type(mesh))

        try:
            import torch
        except ModuleNotFoundError as exc:
            raise StableZero123NovelViewError(
                "PyTorch is required for Stable Zero123 inference."
            ) from exc

        from avroom_object_removal.ai_engines.reconstruction_3d.reconstruction_image_input import (
            to_pil_rgba,
        )

        rgba = to_pil_rgba(image)
        prep = prepare_cutout_for_model(rgba, model_size=self._model_size)
        model_input = rgba_to_rgb_on_white(prep.model_image)

        target_elevation = elevation_deg + relative_elevation_deg
        pose = [target_elevation, azimuth_deg, radius]
        logger.info(
            "Stable Zero123 synthesize: pose=%s steps=%d seed=%d",
            pose,
            self._num_inference_steps,
            seed,
        )

        pipe = _load_zero123_pipeline(self._model_id, self._device)
        generator = torch.Generator(device=self._device).manual_seed(seed)

        try:
            result = pipe(
                input_imgs=model_input,
                prompt_imgs=model_input,
                poses=[pose],
                height=self._model_size,
                width=self._model_size,
                num_inference_steps=self._num_inference_steps,
                guidance_scale=self._guidance_scale,
                generator=generator,
            )
        except Exception as exc:
            logger.exception("Stable Zero123 inference failed")
            raise StableZero123NovelViewError(
                f"Stable Zero123 inference failed: {exc}"
            ) from exc

        generated = result.images[0]
        if not isinstance(generated, Image.Image):
            raise StableZero123NovelViewError(
                f"Unexpected pipeline output type: {type(generated)!r}"
            )

        model_rgba = rgb_to_rgba_with_white_background(generated)
        output_bgra = composite_model_output_on_canvas(model_rgba, prep)
        logger.info(
            "Stable Zero123 synthesize complete: shape=%s azimuth=%.1f",
            output_bgra.shape,
            azimuth_deg,
        )
        return output_bgra
