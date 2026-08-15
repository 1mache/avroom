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

GOOD_LABEL: str = "photorealistic room"
BAD_LABELS: tuple[str, ...] = (
    "smeared blob",
    "unrealistic shaped object",
)
VERIFY_LABELS: tuple[str, ...] = (GOOD_LABEL, *BAD_LABELS)

ScoreFn = Callable[[Image.Image, tuple[str, ...]], dict[str, float]]


class ClipLabelInpaintingVerificationStrategy(InpaintingVerificationStrategy):
    """Zero-shot CLIP labels on a padded mask crop.

    Pass when the good label has the highest softmax score. On fail, echo the
    input :class:`InpaintSdParams` as JSON (v1 does not invent new knobs).
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
        return InpaintingVerificationResult(
            ok=ok,
            param_fixes_json=params.to_json(),
            scores=scores,
            winner_label=winner,
        )
