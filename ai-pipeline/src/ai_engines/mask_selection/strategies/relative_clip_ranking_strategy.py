from __future__ import annotations

from typing import Sequence

from ..mask_selection_strategy import MaskSelectionContext, MaskSelectionStrategy, ScoredCandidate


class RelativeClipRankingStrategy(MaskSelectionStrategy):
    """Relative strategy: all scored candidates are eligible.

    This intentionally avoids any absolute pass/fail elimination on the gray
    CLIP crops. The selection happens via ranking + tie-band (and optionally
    Gemini tie-break) rather than hard gates.
    """

    def eligible_indices(
        self, candidates: Sequence[ScoredCandidate], ctx: MaskSelectionContext
    ) -> tuple[int, ...]:
        del ctx
        return tuple(candidate.index for candidate in candidates)

    def reason_for(
        self,
        index: int,
        *,
        eligible: bool,
        clip_checks: dict[str, float] | None = None,
    ) -> str:
        del index, clip_checks
        return "ranked" if eligible else "not_ranked"

