from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

import numpy as np


@dataclass(frozen=True)
class TiebreakRequest:
    """Inputs for disambiguating CLIP-tied cutout candidates."""

    scene_bgr: np.ndarray
    click_xy: tuple[int, int]
    finalist_indices: tuple[int, ...]
    cutout_crops_bgr: dict[int, np.ndarray]
    clip_averages: dict[int, float]
    refined_masks: dict[int, np.ndarray] | None = None
    click_xys: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class TiebreakResult:
    """Outcome of a tie-break among CLIP finalists."""

    candidate_index: int
    reason: str
    method: Literal["gemini", "clip_fallback"]


class MaskSelectionTiebreakStrategy(ABC):
    """Pick one candidate index when CLIP scores cluster."""

    @abstractmethod
    def pick_among(self, request: TiebreakRequest) -> TiebreakResult:
        """Return the chosen global candidate index."""
