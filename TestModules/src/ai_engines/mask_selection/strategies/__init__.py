from __future__ import annotations

from .absolute_clip_gate_strategy import AbsoluteClipGateStrategy
from .gemini_cutout_all_candidates_tiebreak_strategy import (
    GeminiCutoutAllCandidatesTiebreakStrategy,
)
from .relative_clip_ranking_strategy import RelativeClipRankingStrategy
from .scene_consensus_mask_selection_strategy import SceneConsensusMaskSelectionStrategy

__all__ = [
    "AbsoluteClipGateStrategy",
    "GeminiCutoutAllCandidatesTiebreakStrategy",
    "RelativeClipRankingStrategy",
    "SceneConsensusMaskSelectionStrategy",
]
