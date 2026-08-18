from __future__ import annotations

import logging
from typing import Callable

import cv2
import numpy as np
from PIL import Image

from ...content_validation.strategies.clip_zero_shot_content_validation_strategy import (
    ClipZeroShotContentValidationStrategy,
)
from ..crop import crop_around_mask
from ..inpaint_sd_params import InpaintSdParams
from ..inpainting_verification_result import InpaintingVerificationResult
from ..inpainting_verification_strategy import InpaintingVerificationStrategy

logger = logging.getLogger(__name__)

GOOD_LABEL: str = "a photo of clean seamless floor or wall texture with even lighting"
BAD_LABELS: tuple[str, ...] = (
    "a photo of a dark blurry leftover shadow or ghost stain on the floor",
    "a photo of a smeared inpainting blob",
)
VERIFY_LABELS: tuple[str, ...] = (GOOD_LABEL, *BAD_LABELS)
_RETRY_PROMPT_SUFFIX: str = (
    ", seamless matching surrounding texture, even lighting, no leftover shadow"
)
_RETRY_NEGATIVE_SUFFIX: str = ", leftover shadow, ghost stain, dark oval, blurry smudge"
_RETRY_STRENGTH_BUMP: float = 0.2
_RETRY_STRENGTH_CAP: float = 0.75
_CLIP_FALLBACK_MASK_DILATE: int = 10
_CLIP_FALLBACK_COMPOSE_DILATE: int = 8

ScoreFn = Callable[[Image.Image, tuple[str, ...]], dict[str, float]]


class ClipLabelInpaintingVerificationStrategy(InpaintingVerificationStrategy):
    """Zero-shot CLIP labels on a padded mask crop.

    Pass when the good (clean texture) label wins. On fail, bump strength and
    append shadow-avoidance text so Hybrid's retry is not a no-op replay.
    """

    def __init__(
        self,
        *,
        score_fn: ScoreFn | None = None,
        pad_ratio: float | None = None,
    ) -> None:
        self._score_fn = score_fn
        self._pad_ratio = pad_ratio
        self._clip: ClipZeroShotContentValidationStrategy | None = None
        logger.info("ClipLabelInpaintingVerificationStrategy configured")

    def _score(self, pil_image: Image.Image, labels: tuple[str, ...]) -> dict[str, float]:
        if self._score_fn is not None:
            return self._score_fn(pil_image, labels)
        if self._clip is None:
            self._clip = ClipZeroShotContentValidationStrategy()
        return self._clip.score_labels(pil_image, labels)

    def verify(
        self,
        image: np.ndarray,
        mask: np.ndarray,
        params: InpaintSdParams,
    ) -> InpaintingVerificationResult:
        crop = crop_around_mask(image, mask) if self._pad_ratio is None else crop_around_mask(
            image, mask, pad_ratio=self._pad_ratio
        )
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)
        scores = self._score(pil_image, VERIFY_LABELS)
        winner = max(VERIFY_LABELS, key=lambda label: scores.get(label, 0.0))
        ok = winner == GOOD_LABEL
        logger.info(
            "Inpaint CLIP verify ok=%s winner=%s scores=%s",
            ok,
            winner,
            scores,
        )
        fixes = params if ok else _retry_params(params)
        return InpaintingVerificationResult(
            ok=ok,
            param_fixes_json=fixes.to_json(),
            scores=scores,
            winner_label=winner,
        )


def _retry_params(params: InpaintSdParams) -> InpaintSdParams:
    """Nudge SD knobs toward filling leftover shadows on the next pass."""
    prompt = params.prompt
    if _RETRY_PROMPT_SUFFIX not in prompt:
        prompt = prompt + _RETRY_PROMPT_SUFFIX
    negative = params.negative_prompt
    if _RETRY_NEGATIVE_SUFFIX not in negative:
        negative = negative + _RETRY_NEGATIVE_SUFFIX
    return InpaintSdParams(
        prompt=prompt,
        negative_prompt=negative,
        strength=min(_RETRY_STRENGTH_CAP, params.strength + _RETRY_STRENGTH_BUMP),
        num_inference_steps=params.num_inference_steps,
        guidance_scale=params.guidance_scale,
        mask_dilate_pixels=_CLIP_FALLBACK_MASK_DILATE,
        compose_dilate_pixels=_CLIP_FALLBACK_COMPOSE_DILATE,
    )
