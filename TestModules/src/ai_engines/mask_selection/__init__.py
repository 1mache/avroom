from __future__ import annotations

from .clip_cutout_checks import (
    CLIP_CUTOUT_CHECKS,
    CHECK_PASS_THRESHOLD,
    ClipCutoutCheck,
    LabelScorer,
    average_positive_score,
    first_failing_check,
    passes_all_checks,
    score_cutout_checks,
)
from .mask_selection_strategy import MaskSelectionStrategy, ScoredCandidate
from .mask_selection_tiebreak_strategy import (
    MaskSelectionTiebreakStrategy,
    TiebreakRequest,
    TiebreakResult,
)
from .strategies.gemini_cutout_tiebreak_strategy import GeminiCutoutTiebreakStrategy
from .strategies import (
    AbsoluteClipGateStrategy,
    GeminiCutoutAllCandidatesTiebreakStrategy,
    RelativeClipRankingStrategy,
    SceneConsensusMaskSelectionStrategy,
)

__all__ = [
    "CLIP_CUTOUT_CHECKS",
    "CHECK_PASS_THRESHOLD",
    "ClipCutoutCheck",
    "GeminiCutoutTiebreakStrategy",
    "GeminiCutoutAllCandidatesTiebreakStrategy",
    "LabelScorer",
    "MaskSelectionStrategy",
    "ScoredCandidate",
    "MaskSelectionTiebreakStrategy",
    "TiebreakRequest",
    "TiebreakResult",
    "average_positive_score",
    "first_failing_check",
    "passes_all_checks",
    "score_cutout_checks",
    "AbsoluteClipGateStrategy",
    "RelativeClipRankingStrategy",
    "SceneConsensusMaskSelectionStrategy",
]
