from __future__ import annotations

import logging

import numpy as np

from .content_validation_result import ContentValidationResult
from .content_validation_strategy import ContentValidationStrategy
from .strategies.clip_zero_shot_content_validation_strategy import (
    ClipZeroShotContentValidationStrategy,
)

logger = logging.getLogger(__name__)


class ContentValidationFacade:
    """Public entry point for ML-based upload content validation.

    Holds exactly one :class:`ContentValidationStrategy`. The default backend
    is :class:`ClipZeroShotContentValidationStrategy`.
    """

    def __init__(self, strategy: ContentValidationStrategy | None = None) -> None:
        self._strategy: ContentValidationStrategy = strategy or ClipZeroShotContentValidationStrategy()
        logger.info(
            "ContentValidationFacade ready (strategy=%s)",
            type(self._strategy).__name__,
        )

    @property
    def strategy(self) -> ContentValidationStrategy:
        return self._strategy

    def validate(self, image: np.ndarray) -> ContentValidationResult:
        """Run content validation on a decoded BGR ``uint8`` image."""
        return self._strategy.validate(image)
