from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np

from ....utils.debug_image_saver import DebugImageSaver
from ....utils.mask_refiner import MaskRefiner
from ...inpainting_verification.crop import (
    GEMINI_CROP_PAD_RATIO,
    INPAINT_VERIFY_CROP_PAD_RATIO as _CROP_PAD_RATIO,
    build_verify_crops,
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
        self._mask_refiner = MaskRefiner()
        logger.info("Hybrid Pipeline initialized successfully.")

    @staticmethod
    def _params_trace(params: InpaintSdParams) -> dict[str, Any]:
        return {
            "prompt": params.prompt,
            "negative_prompt": params.negative_prompt,
            "strength": params.strength,
            "num_inference_steps": params.num_inference_steps,
            "guidance_scale": params.guidance_scale,
            "mask_dilate_pixels": params.mask_dilate_pixels,
            "compose_dilate_pixels": params.compose_dilate_pixels,
        }

    @staticmethod
    def _mask_pixel_count(mask: np.ndarray) -> int:
        if mask.ndim == 3:
            mask = mask[:, :, 0]
        if mask.dtype == np.uint8 or (mask.size and float(mask.max()) > 1.0):
            return int(np.count_nonzero(mask > 127))
        return int(np.count_nonzero(mask > 0.5))

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
        inpaint_out = kwargs.pop("inpaint_out", None)
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

        cumulative_mask_dilate = 0
        cumulative_compose_dilate = 0
        last_verdict_ok = False

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
            verdict = self._verifier.verify(
                candidate,
                mask,
                params,
                original_image=image,
            )
            last_verdict_ok = verdict.ok
            next_params: InpaintSdParams | None = None
            if not verdict.ok:
                try:
                    next_params = InpaintSdParams.from_json(verdict.param_fixes_json)
                except (KeyError, ValueError, TypeError):
                    next_params = None
            mask_px = self._mask_pixel_count(mask)
            if not verdict.ok and next_params is not None:
                logger.info(
                    "Inpaint verify ok=%s attempt=%d retries_left=%d mask_px=%d "
                    "next_strength=%s next_mask_dilate=%s next_compose_dilate=%s",
                    verdict.ok,
                    attempt_index,
                    retries_left,
                    mask_px,
                    next_params.strength,
                    next_params.mask_dilate_pixels,
                    next_params.compose_dilate_pixels,
                )
            else:
                logger.info(
                    "Inpaint verify ok=%s attempt=%d retries_left=%d mask_px=%d",
                    verdict.ok,
                    attempt_index,
                    retries_left,
                    mask_px,
                )
            if verify_trace is not None:
                verify_original_crop: np.ndarray | None = None
                clip_crop = crop_around_mask(candidate, mask)
                try:
                    verify_original_crop, clip_crop, _window = build_verify_crops(
                        image,
                        candidate,
                        mask,
                        pad_ratio=GEMINI_CROP_PAD_RATIO,
                    )
                except (ValueError, IndexError):
                    verify_original_crop = None
                verify_trace.append(
                    {
                        "attempt_index": attempt_index,
                        "ok": verdict.ok,
                        "scores": dict(verdict.scores),
                        "winner_label": verdict.winner_label,
                        "sd_skipped": sd_skipped and attempt_index == 0,
                        "params": self._params_trace(params),
                        "param_fixes_json": verdict.param_fixes_json,
                        "mask_dilate_pixels": next_params.mask_dilate_pixels if next_params else 0,
                        "compose_dilate_pixels": next_params.compose_dilate_pixels if next_params else 0,
                        "mask_pixel_count": mask_px,
                        "next_params": self._params_trace(next_params) if next_params else None,
                        "candidate_bgr": candidate.copy(),
                        "verify_original_crop_bgr": (
                            verify_original_crop.copy()
                            if verify_original_crop is not None
                            else None
                        ),
                        "clip_crop_bgr": clip_crop.copy(),
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
                retry_params = InpaintSdParams.from_json(verdict.param_fixes_json)
            except (KeyError, ValueError, TypeError):
                logger.warning("Ignoring unverifiable param JSON; replaying last params.")
                retry_params = params
            retry_params = retry_params.clamp_dilate_fields(
                cumulative_mask_dilate=cumulative_mask_dilate,
            )
            cumulative_compose_dilate += retry_params.compose_dilate_pixels
            if retry_params.mask_dilate_pixels > 0:
                mask_before = self._mask_pixel_count(mask)
                mask = self._mask_refiner.dilate_mask(mask, pixels=retry_params.mask_dilate_pixels)
                cumulative_mask_dilate += retry_params.mask_dilate_pixels
                mask_after = self._mask_pixel_count(mask)
                logger.info(
                    "Hybrid mask dilate: +%d px cumulative=%d pixels %d->%d",
                    retry_params.mask_dilate_pixels,
                    cumulative_mask_dilate,
                    mask_before,
                    mask_after,
                )
                primary_result = self._primary.inpaint(image, mask)
                self._image_saver.save("debug_lama_output", primary_result)
            params = InpaintSdParams(
                prompt=retry_params.prompt,
                negative_prompt=retry_params.negative_prompt,
                strength=retry_params.strength,
                num_inference_steps=retry_params.num_inference_steps,
                guidance_scale=retry_params.guidance_scale,
            )
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
        if inpaint_out is not None:
            inpaint_out["verification_ok"] = last_verdict_ok
            inpaint_out["compose_dilate_pixels"] = cumulative_compose_dilate
            inpaint_out["final_inpaint_mask"] = mask.copy()
        if not last_verdict_ok:
            logger.warning("Inpaint verify finished with verification_ok=False")
        logger.info("Hybrid Pipeline completed successfully.")
        return final_result
