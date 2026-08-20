from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from avroom_object_removal.ai_engines.mask_selection import (
    RelativeClipRankingStrategy,
    ScoredCandidate,
)
from avroom_object_removal.ai_engines.mask_selection.mask_selection_strategy import (
    MaskSelectionContext,
)


def test_relative_clip_ranking_strategy_eligible_indices() -> None:
    strategy = RelativeClipRankingStrategy()
    candidates = [
        ScoredCandidate(
            index=0,
            avg_score=0.1,
            clip_checks={"complete": 0.1},
            clip_crop_bgr=np.zeros((2, 2, 3), dtype=np.uint8),
        ),
        ScoredCandidate(
            index=1,
            avg_score=0.2,
            clip_checks={"complete": 0.9},
            clip_crop_bgr=np.zeros((2, 2, 3), dtype=np.uint8),
        ),
    ]
    ctx = MaskSelectionContext(cutouts_bgra=[], click_xy=(0, 0), scene_bgr=None, depth_map=None)
    assert strategy.eligible_indices(candidates, ctx) == (0, 1)


def test_relative_clip_ranking_strategy_reason_for() -> None:
    strategy = RelativeClipRankingStrategy()
    assert strategy.reason_for(123, eligible=True, clip_checks=None) == "ranked"
    assert strategy.reason_for(123, eligible=False, clip_checks=None) == "not_ranked"


def test_relative_clip_ranking_strategy_does_not_inspect_clip_checks() -> None:
    strategy = RelativeClipRankingStrategy()
    clip_checks = MagicMock()
    assert strategy.reason_for(0, eligible=True, clip_checks=clip_checks) == "ranked"

