from __future__ import annotations

import logging
from typing import Sequence

from ..clip_cutout_checks import first_failing_check
from ..mask_selection_strategy import MaskSelectionContext, MaskSelectionStrategy, ScoredCandidate

logger = logging.getLogger(__name__)


class AbsoluteClipGateStrategy(MaskSelectionStrategy):
    """Eligibility matches the current absolute CLIP gate logic.

    A candidate is eligible only if it passes *all* configured CLIP cutout
    checks (thresholds live in ``clip_cutout_checks.py``).
    """

    def eligible_indices(
        self, candidates: Sequence[ScoredCandidate], ctx: MaskSelectionContext
    ) -> tuple[int, ...]:
        del ctx
        eligible: list[int] = []
        for candidate in candidates:
            if first_failing_check(candidate.clip_checks) is None:
                eligible.append(candidate.index)
        return tuple(eligible)

    def reason_for(
        self,
        index: int,
        *,
        eligible: bool,
        clip_checks: dict[str, float] | None = None,
    ) -> str:
        if eligible:
            return "scored"
        if clip_checks is None:
            return "not_eligible"
        fail_key = first_failing_check(clip_checks)
        if fail_key is None:
            return "not_eligible"
        return f"clip_fail:{fail_key}"

