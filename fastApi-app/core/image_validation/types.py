from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image


@dataclass
class ImageValidationContext:
    """Shared decode state for one upload validation pass."""

    file_bytes: bytes
    filename: str | None
    content_type: str | None
    pil_image: Image.Image
    rgb_array: np.ndarray
    bgr_array: np.ndarray
    width: int
    height: int
    alpha_opaque_ratio: float = 1.0


@dataclass(frozen=True)
class TechnicalCheckResult:
    """Outcome of one deterministic technical check."""

    name: str
    passed: bool
    score: float | None = None
    message: str = ""


class ImageValidationError(ValueError):
    """Raised when one or more technical checks fail."""

    def __init__(self, results: list[TechnicalCheckResult]) -> None:
        failed = [result for result in results if not result.passed]
        detail = "; ".join(f"{result.name}: {result.message}" for result in failed)
        super().__init__(detail)
        self.failed_results = failed
