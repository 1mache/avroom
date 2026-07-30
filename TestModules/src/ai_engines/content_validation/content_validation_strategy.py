from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from .content_validation_result import ContentValidationResult


class ContentValidationStrategy(ABC):
    """Abstract Strategy for ML-based upload content validation.

    Implementations inspect a decoded BGR ``uint8`` image and return a
    :class:`ContentValidationResult`. Concrete strategies live under
    :mod:`avroom_object_removal.ai_engines.content_validation.strategies`.
    """

    @abstractmethod
    def validate(self, image: np.ndarray) -> ContentValidationResult:
        """Run content checks on ``image`` and return a structured result."""
        raise NotImplementedError
