from __future__ import annotations

import sys
from unittest.mock import MagicMock

import numpy as np
from PIL import Image

sys.modules.setdefault("torch", MagicMock())
sys.modules.setdefault("transformers", MagicMock())

from avroom_object_removal import (  # noqa: E402
    ClipZeroShotContentValidationStrategy,
    select_best_cutout,
)
from avroom_object_removal.ai_engines.mask_selection.clip_cutout_checks import (  # noqa: E402
    CLIP_CUTOUT_CHECKS,
)
from avroom_object_removal.ai_engines.mask_selection.mask_selection_tiebreak_strategy import (  # noqa: E402
    TiebreakRequest,
    TiebreakResult,
)
from avroom_object_removal.ai_engines.mask_selection.strategies.relative_clip_ranking_strategy import (
    RelativeClipRankingStrategy,
)
from avroom_object_removal.ai_engines.mask_selection.strategies.gemini_cutout_all_candidates_tiebreak_strategy import (  # noqa: E402
    GeminiCutoutAllCandidatesTiebreakStrategy,
)

_H = 100
_W = 100
_SCENE = np.zeros((_H, _W, 3), dtype=np.uint8)


def _bgra(*, alpha_rect: tuple[int, int, int, int]) -> np.ndarray:
    image = np.zeros((_H, _W, 4), dtype=np.uint8)
    x0, y0, x1, y1 = alpha_rect
    image[y0:y1, x0:x1, :3] = (40, 80, 120)
    image[y0:y1, x0:x1, 3] = 255
    return image


def _uniform_checks(value: float) -> dict[str, float]:
    return {check.key: value for check in CLIP_CUTOUT_CHECKS}


def _scorer(
    check_probs_by_index: dict[int, dict[str, float]],
) -> ClipZeroShotContentValidationStrategy:
    call_index = {"n": 0}

    def fake_score(_pil: Image.Image, labels: tuple[str, ...]) -> dict[str, float]:
        index = call_index["n"]
        call_index["n"] += 1
        per_check = check_probs_by_index.get(index, _uniform_checks(0.60))
        distribution: dict[str, float] = {}
        for check in CLIP_CUTOUT_CHECKS:
            positive_p = per_check.get(check.key, 0.60)
            distribution[check.positive] = positive_p
            distribution[check.negative] = 1.0 - positive_p
        for label in labels:
            distribution.setdefault(label, 0.0)
        return distribution

    return ClipZeroShotContentValidationStrategy(score_fn=fake_score)


def test_all_candidates_strategy_has_marker() -> None:
    strategy = GeminiCutoutAllCandidatesTiebreakStrategy(api_key="test-key")
    assert strategy.select_all_candidates is True


def test_select_all_candidates_sends_every_eligible_index_to_gemini() -> None:
    viable = (20, 20, 50, 50)
    cutouts = [_bgra(alpha_rect=viable) for _ in range(6)]
    seen_requests: list[TiebreakRequest] = []

    class RecordingAllCandidatesStrategy(GeminiCutoutAllCandidatesTiebreakStrategy):
        def pick_among(self, request: TiebreakRequest) -> TiebreakResult:
            seen_requests.append(request)
            return TiebreakResult(
                candidate_index=3,
                reason="mock gemini",
                method="gemini",
            )

    tiebreaker = RecordingAllCandidatesStrategy(api_key="test-key")
    result = select_best_cutout(
        cutouts,
        click_xy=(30, 30),
        scorer=_scorer({index: _uniform_checks(0.90 - index * 0.10) for index in range(6)}),
        scene_bgr=_SCENE,
        tiebreaker=tiebreaker,
        selection_strategy=RelativeClipRankingStrategy(),
    )

    assert result.winner_index == 3
    assert result.finalist_indices == (0, 1, 2, 3, 4, 5)
    assert len(seen_requests) == 1
    assert seen_requests[0].finalist_indices == (0, 1, 2, 3, 4, 5)


def test_tie_band_still_limits_finalists_without_all_candidates_marker() -> None:
    viable = (20, 20, 50, 50)
    cutouts = [_bgra(alpha_rect=viable), _bgra(alpha_rect=viable), _bgra(alpha_rect=viable)]
    seen_requests: list[TiebreakRequest] = []

    tiebreaker = MagicMock()
    tiebreaker.select_all_candidates = False
    tiebreaker.pick_among.side_effect = lambda request: (
        seen_requests.append(request),
        TiebreakResult(candidate_index=1, reason="mock", method="gemini"),
    )[1]

    result = select_best_cutout(
        cutouts,
        click_xy=(30, 30),
        scorer=_scorer(
            {0: _uniform_checks(0.80), 1: _uniform_checks(0.50), 2: _uniform_checks(0.40)}
        ),
        scene_bgr=_SCENE,
        tiebreaker=tiebreaker,
        selection_strategy=RelativeClipRankingStrategy(),
    )

    assert result.finalist_indices == (0,)
    tiebreaker.pick_among.assert_not_called()
