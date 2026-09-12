from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class ScoredCandidate:
    """One SAM candidate after CLIP scoring on the candidate crop."""

    index: int
    avg_score: float
    clip_checks: dict[str, float]
    clip_crop_bgr: np.ndarray | None


@dataclass(frozen=True)
class MaskSelectionContext:
    """Context available to mask-selection strategies."""

    cutouts_bgra: Sequence[np.ndarray]
    click_xy: tuple[int, int]
    scene_bgr: np.ndarray | None = None
    depth_map: np.ndarray | None = None
    click_xys: tuple[tuple[int, int], ...] = ()


class MaskSelectionStrategy(ABC):
    """Policy for deciding which scored candidates are eligible to win.

    Strategies can optionally skip CLIP scoring (`needs_clip=False`) and instead
    compute ranking scores from scene/depth/mask geometry.
    """

    def needs_clip(self) -> bool:
        return True

    def rank_scores(
        self,
        candidates: Sequence[ScoredCandidate],
        ctx: MaskSelectionContext,
    ) -> dict[int, float]:
        del ctx
        return {candidate.index: candidate.avg_score for candidate in candidates}

    @abstractmethod
    def eligible_indices(
        self,
        candidates: Sequence[ScoredCandidate],
        ctx: MaskSelectionContext,
    ) -> tuple[int, ...]:
        """Return global candidate indices that are eligible to compete."""

    @abstractmethod
    def reason_for(
        self,
        index: int,
        *,
        eligible: bool,
        clip_checks: dict[str, float] | None = None,
    ) -> str:
        """Return a debug reason tag for one candidate."""

