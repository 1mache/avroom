from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np

from ....utils.debug_image_saver import DebugImageSaver
from ...inpainting_verification.crop import (
    INPAINT_VERIFY_CROP_PAD_RATIO as _CROP_PAD_RATIO,
    crop_around_mask,
)
from ...inpainting_verification.inpaint_sd_params import InpaintSdParams
from ...inpainting_verification.inpainting_verification_facade import (
    InpaintingVerificationFacade,
)
from ...inpainting_verification.inpainting_verification_strategy import (
    InpaintingVerificationStrategy,
)
from ..image_inpainting_strategy import ImageInpaintingStrategy
from .lama_inpainting_strategy import LamaInpaintingStrategy
from .stable_diffusion_inpainting_strategy import StableDiffusionInpaintingStrategy

logger = logging.getLogger(__name__)


class HybridInpaintingStrategy(ImageInpaintingStrategy):
    """Two-stage inpainting strategy that composes LaMa + Stable Diffusion.

    Phase 1 (LaMa): cheap structural removal that avoids hallucinating new
    content. Phase 2 (SD, optional): texture refinement at low ``strength``
    so reimagined edges blend with surroundings without inventing furniture.

    After each candidate (including LaMa-only when SD is skipped), an
    :class:`InpaintingVerificationFacade` (Gemini default) judges the result.
    Failures replay SD with the returned JSON params up to
    ``INPAINT_VERIFY_MAX_RETRIES``.
    """

    SD_SKIP_THRESHOLD: float = 0.2
    SHARPEN_SIGMA: float = 0.8
    SHARPEN_AMOUNT: float = 0.6
    INPAINT_VERIFY_MAX_RETRIES: int = 2
    INPAINT_VERIFY_CROP_PAD_RATIO: float = _CROP_PAD_RATIO

    def __init__(
        self,
        primary: ImageInpaintingStrategy | None = None,
        refiner: ImageInpaintingStrategy | None = None,
        verifier: InpaintingVerificationFacade | InpaintingVerificationStrategy | None = None,
    ) -> None:
        logger.info("Initializing Hybrid Inpainting Pipeline...")
        self._primary: ImageInpaintingStrategy = primary or LamaInpaintingStrategy()
        self._refiner: ImageInpaintingStrategy = refiner or StableDiffusionInpaintingStrategy()
        self._verifier: InpaintingVerificationFacade = (
            verifier
            if isinstance(verifier, InpaintingVerificationFacade)
            else InpaintingVerificationFacade(strategy=verifier)
        )
        self._image_saver = DebugImageSaver()
        logger.info("Hybrid Pipeline initialized successfully.")

    def _snapshot_params(self, kwargs: dict[str, Any], strength: float) -> InpaintSdParams:
        refiner = self._refiner
        prompt = str(
            kwargs.get(
                "prompt",
                getattr(refiner, "_prompt", StableDiffusionInpaintingStrategy.DEFAULT_PROMPT),
            )
        )
        negative = str(
            kwargs.get(
                "negative_prompt",
                getattr(
                    refiner,
                    "_negative_prompt",
                    StableDiffusionInpaintingStrategy.DEFAULT_NEGATIVE_PROMPT,
                ),
            )
        )
        return InpaintSdParams(
            prompt=prompt,
            negative_prompt=negative,
            strength=strength,
            num_inference_steps=int(kwargs.get("num_inference_steps", 30)),
            guidance_scale=float(kwargs.get("guidance_scale", 10.0)),
        )

    def _run_sd(self, image: np.ndarray, mask: np.ndarray, params: InpaintSdParams) -> np.ndarray:
        logger.info(
            "Hybrid SD pass: strength=%s steps=%s guidance=%s prompt=%r negative=%r",
            params.strength,
            params.num_inference_steps,
            params.guidance_scale,
            params.prompt,
            params.negative_prompt,
        )
        return self._refiner.inpaint(
            image,
            mask,
            prompt=params.prompt,
            strength=params.strength,
            negative_prompt=params.negative_prompt,
            num_inference_steps=params.num_inference_steps,
            guidance_scale=params.guidance_scale,
        )

    def inpaint(self, image: np.ndarray, mask: np.ndarray, **kwargs: Any) -> np.ndarray:
        verify_trace = kwargs.pop("verify_trace", None)
        if mask.ndim == 3:
            mask = mask[:, :, 0]

        if mask.shape[:2] != image.shape[:2]:
            mask = cv2.resize(
                mask,
                (image.shape[1], image.shape[0]),
                interpolation=cv2.INTER_NEAREST,
            )
            thresh = 0.5 if mask.max() <= 1.0 else 127
            mask = (mask > thresh).astype(np.uint8) * 255

        logger.info("--- Hybrid Pipeline Phase 1: Structural removal (LaMa) ---")
        primary_result = self._primary.inpaint(image, mask)
        self._image_saver.save("debug_lama_output", primary_result)

        logger.info("--- Hybrid Pipeline Phase 2: Texture refinement (SD) ---")
        dynamic_strength = float(kwargs.get("strength", 0.35))
        params = self._snapshot_params(kwargs, dynamic_strength)

        sd_skipped = dynamic_strength <= self.SD_SKIP_THRESHOLD
        if sd_skipped:
            candidate = primary_result.copy()
            logger.info("Skipping SD (strength <= 0.2); using primary result only.")
        else:
            candidate = self._run_sd(primary_result, mask, params)

        retries_left = self.INPAINT_VERIFY_MAX_RETRIES
        attempt_index = 0
        while True:
            verdict = self._verifier.verify(candidate, mask, params)
            logger.info(
                "Inpaint verify ok=%s retries_left=%d",
                verdict.ok,
                retries_left,
            )
            if verify_trace is not None:
                verify_trace.append(
                    {
                        "attempt_index": attempt_index,
                        "ok": verdict.ok,
                        "scores": dict(verdict.scores),
                        "winner_label": verdict.winner_label,
                        "sd_skipped": sd_skipped and attempt_index == 0,
                        "params": {
                            "prompt": params.prompt,
                            "negative_prompt": params.negative_prompt,
                            "strength": params.strength,
                            "num_inference_steps": params.num_inference_steps,
                            "guidance_scale": params.guidance_scale,
                        },
                        "param_fixes_json": verdict.param_fixes_json,
                        "candidate_bgr": candidate.copy(),
                        "clip_crop_bgr": crop_around_mask(candidate, mask).copy(),
                        "lama_bgr": primary_result.copy() if attempt_index == 0 else None,
                    }
                )
            if verdict.ok:
                break
            if retries_left <= 0:
                logger.warning("Inpaint verify exhausted retries; keeping last candidate.")
                break
            retries_left -= 1
            attempt_index += 1
            try:
                params = InpaintSdParams.from_json(verdict.param_fixes_json)
            except (KeyError, ValueError, TypeError):
                logger.warning("Ignoring unverifiable param JSON; replaying last params.")
            candidate = self._run_sd(primary_result, mask, params)
            sd_skipped = False

        final_result = candidate

        # Re-align result/mask before any boolean indexing.
        if final_result.shape[:2] != image.shape[:2]:
            final_result = cv2.resize(
                final_result,
                (image.shape[1], image.shape[0]),
                interpolation=cv2.INTER_LANCZOS4,
            )
        if mask.shape[:2] != final_result.shape[:2]:
            mask = cv2.resize(
                mask,
                (final_result.shape[1], final_result.shape[0]),
                interpolation=cv2.INTER_NEAREST,
            )
            thresh = 0.5 if mask.max() <= 1.0 else 127
            mask = (mask > thresh).astype(np.uint8) * 255

        # Unsharp mask: pulls reimagined edges toward surrounding contrast.
        blurred = cv2.GaussianBlur(final_result, (0, 0), self.SHARPEN_SIGMA)
        as_float = final_result.astype(np.float32)
        final_result = np.clip(
            as_float + self.SHARPEN_AMOUNT * (as_float - blurred.astype(np.float32)),
            0,
            255,
        ).astype(np.uint8)

        # Color-nudge the mask interior toward the boundary mean. We avoid
        # touching the dilated edge band so reimagined geometry isn't warped.
        mask_bool = (mask > 127) if (mask.dtype == np.uint8 or mask.max() > 1) else (mask > 0.5)
        if mask_bool.any() and len(final_result.shape) == 3:
            mask_uint = (mask * 255).astype(np.uint8) if mask.max() <= 1 else mask.astype(np.uint8)
            kernel = np.ones((3, 3), np.uint8)
            boundary = (cv2.dilate(mask_uint, kernel) > 0) & (~mask_bool)
            interior_only = cv2.erode(mask_uint, np.ones((7, 7), np.uint8)) > 127
            if boundary.any() and interior_only.any():
                boundary_mean = final_result[boundary].mean(axis=0)
                inside_mean = final_result[interior_only].mean(axis=0)
                shift = (boundary_mean.astype(np.float32) - inside_mean.astype(np.float32)) * 0.35
                out = final_result.astype(np.float32)
                out[interior_only] = np.clip(out[interior_only] + shift, 0, 255)
                final_result = out.astype(np.uint8)

        self._image_saver.save("debug_sd_output", final_result)
        logger.info("Hybrid Pipeline completed successfully.")
        return final_result
