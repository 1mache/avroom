from __future__ import annotations

import logging
from typing import Any

from .gemini_cutout_tiebreak_strategy import CompleteFn, GeminiCutoutTiebreakStrategy

logger = logging.getLogger(__name__)


class GeminiCutoutAllCandidatesTiebreakStrategy(GeminiCutoutTiebreakStrategy):
    """Gemini primary picker: caller passes every eligible candidate as finalists.

    ``select_best_cutout`` skips ``TIE_BAND`` filtering when this marker is set.
    CLIP scores are still computed for logging and Gemini failure fallback only.
    """

    select_all_candidates: bool = True

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_id: str | None = None,
        complete_fn: CompleteFn | None = None,
    ) -> None:
        super().__init__(api_key=api_key, model_id=model_id, complete_fn=complete_fn)
        logger.info("GeminiCutoutAllCandidatesTiebreakStrategy configured (all-candidates mode)")
