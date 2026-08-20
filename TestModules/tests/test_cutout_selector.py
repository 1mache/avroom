from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
from PIL import Image

sys.modules.setdefault("torch", MagicMock())
sys.modules.setdefault("transformers", MagicMock())

from avroom_object_removal import (  # noqa: E402
    ClipZeroShotContentValidationStrategy,
    AbsoluteClipGateStrategy,
    RelativeClipRankingStrategy,
    select_best_cutout,
)
from avroom_object_removal.ai_engines.mask_selection.clip_cutout_checks import (  # noqa: E402
    CLIP_CUTOUT_CHECKS,
)
from avroom_object_removal.ai_engines.mask_selection.mask_selection_tiebreak_strategy import (  # noqa: E402
    TiebreakResult,
)
from avroom_object_removal.core.cutout_selector import _DEBUG_FOLDER  # noqa: E402

_H = 100
_W = 100
_SCENE = np.zeros((_H, _W, 3), dtype=np.uint8)


def _bgra(*, alpha_rect: tuple[int, int, int, int] | None) -> np.ndarray:
    """Build a BGRA cutout. ``alpha_rect`` is ``(x0, y0, x1, y1)`` exclusive."""
    image = np.zeros((_H, _W, 4), dtype=np.uint8)
    if alpha_rect is None:
        return image
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


def test_click_miss_is_prefiltered() -> None:
    cutout = _bgra(alpha_rect=(10, 10, 40, 40))
    result = select_best_cutout(
        [cutout],
        click_xy=(80, 80),
        scorer=_scorer({0: _uniform_checks(0.99)}),
    )
    assert result.winner_index is None
    assert result.scores == (0.0,)
    assert result.reasons == ("click_miss",)


def test_area_too_small_is_prefiltered() -> None:
    cutout = _bgra(alpha_rect=(20, 20, 21, 21))
    result = select_best_cutout(
        [cutout],
        click_xy=(20, 20),
        scorer=_scorer({0: _uniform_checks(0.99)}),
    )
    assert result.winner_index is None
    assert result.scores == (0.0,)


def test_area_too_large_is_prefiltered() -> None:
    cutout = _bgra(alpha_rect=(0, 0, 100, 100))
    result = select_best_cutout(
        [cutout],
        click_xy=(50, 50),
        scorer=_scorer({0: _uniform_checks(0.99)}),
    )
    assert result.winner_index is None
    assert result.scores == (0.0,)


def test_picks_highest_clip_average() -> None:
    viable = (20, 20, 50, 50)
    cutouts = [_bgra(alpha_rect=viable), _bgra(alpha_rect=viable), _bgra(alpha_rect=viable)]
    result = select_best_cutout(
        cutouts,
        click_xy=(30, 30),
        scorer=_scorer(
            {
                0: _uniform_checks(0.56),
                1: _uniform_checks(0.82),
                2: _uniform_checks(0.70),
            }
        ),
        selection_strategy=RelativeClipRankingStrategy(),
    )
    assert result.winner_index == 1
    assert result.scores == (0.56, 0.82, 0.70)
    assert result.reasons == ("ranked", "winner", "ranked")
    assert result.tiebreak_method == "none"


def test_clip_gate_rejects_failing_check() -> None:
    viable = (20, 20, 50, 50)
    cutouts = [_bgra(alpha_rect=viable), _bgra(alpha_rect=viable)]
    failing = _uniform_checks(0.60)
    failing["complete"] = 0.40
    result = select_best_cutout(
        cutouts,
        click_xy=(30, 30),
        scorer=_scorer({0: failing, 1: _uniform_checks(0.70)}),
        selection_strategy=AbsoluteClipGateStrategy(),
    )
    assert result.winner_index == 1
    assert result.reasons[0] == "clip_fail:complete"


def test_clear_winner_skips_tiebreaker() -> None:
    viable = (20, 20, 50, 50)
    cutouts = [_bgra(alpha_rect=viable), _bgra(alpha_rect=viable)]
    tiebreaker = MagicMock()
    tiebreaker.pick_among.side_effect = AssertionError("tiebreaker should not run")

    result = select_best_cutout(
        cutouts,
        click_xy=(30, 30),
        scorer=_scorer({0: _uniform_checks(0.60), 1: _uniform_checks(0.90)}),
        selection_strategy=RelativeClipRankingStrategy(),
        scene_bgr=_SCENE,
        tiebreaker=tiebreaker,
    )
    assert result.winner_index == 1
    tiebreaker.pick_among.assert_not_called()


def test_tie_band_invokes_tiebreaker() -> None:
    viable = (20, 20, 50, 50)
    cutouts = [_bgra(alpha_rect=viable), _bgra(alpha_rect=viable)]
    tiebreaker = MagicMock()
    tiebreaker.pick_among.return_value = TiebreakResult(
        candidate_index=1,
        reason="gemini pick",
        method="gemini",
    )

    result = select_best_cutout(
        cutouts,
        click_xy=(30, 30),
        scorer=_scorer({0: _uniform_checks(0.80), 1: _uniform_checks(0.78)}),
        selection_strategy=RelativeClipRankingStrategy(),
        scene_bgr=_SCENE,
        tiebreaker=tiebreaker,
    )
    assert result.winner_index == 1
    assert result.finalist_indices == (0, 1)
    assert result.tiebreak_method == "gemini"
    tiebreaker.pick_among.assert_called_once()


def test_tiebreaker_failure_falls_back_to_clip() -> None:
    viable = (20, 20, 50, 50)
    cutouts = [_bgra(alpha_rect=viable), _bgra(alpha_rect=viable)]
    tiebreaker = MagicMock()
    tiebreaker.pick_among.return_value = TiebreakResult(
        candidate_index=0,
        reason="clip_fallback: bad json",
        method="clip_fallback",
    )

    result = select_best_cutout(
        cutouts,
        click_xy=(30, 30),
        scorer=_scorer({0: _uniform_checks(0.80), 1: _uniform_checks(0.79)}),
        selection_strategy=RelativeClipRankingStrategy(),
        scene_bgr=_SCENE,
        tiebreaker=tiebreaker,
    )
    assert result.winner_index == 0
    assert result.tiebreak_method == "clip_fallback"


def test_relative_picks_highest_when_all_fail_absolute_gate() -> None:
    viable = (20, 20, 50, 50)
    cutouts = [_bgra(alpha_rect=viable), _bgra(alpha_rect=viable)]

    # Make `complete`, `single`, and `not_fragment` fail the absolute gate, but
    # keep `not_scene` as the only differentiator so relative ranking can win.
    cand0 = _uniform_checks(0.02)
    cand0["not_scene"] = 0.95

    cand1 = _uniform_checks(0.02)
    cand1["not_scene"] = 0.80

    result = select_best_cutout(
        cutouts,
        click_xy=(30, 30),
        scorer=_scorer({0: cand0, 1: cand1}),
        selection_strategy=RelativeClipRankingStrategy(),
    )
    assert result.winner_index == 0
    assert result.tiebreak_method == "none"
    assert result.reasons[0] == "winner"
    assert result.reasons[1] == "ranked"


def test_all_candidates_fail_clip_checks_absolute_gate_returns_none() -> None:
    viable = (20, 20, 50, 50)
    cutouts = [_bgra(alpha_rect=viable), _bgra(alpha_rect=viable)]

    low = _uniform_checks(0.02)
    result = select_best_cutout(
        cutouts,
        click_xy=(30, 30),
        scorer=_scorer({0: low, 1: low}),
        selection_strategy=AbsoluteClipGateStrategy(),
    )
    assert result.winner_index is None
    assert all(reason.startswith("clip_fail:") for reason in result.reasons)


def test_debug_dump_writes_selection_json_and_winner() -> None:
    viable = (20, 20, 50, 50)
    cutouts = [_bgra(alpha_rect=viable), _bgra(alpha_rect=viable)]
    select_best_cutout(
        cutouts,
        click_xy=(30, 30),
        scorer=_scorer({0: _uniform_checks(0.56), 1: _uniform_checks(0.82)}),
        selection_strategy=RelativeClipRankingStrategy(),
    )

    debug_dir = Path(__file__).resolve().parents[1] / Path(_DEBUG_FOLDER)
    summary = json.loads((debug_dir / "selection.json").read_text(encoding="utf-8"))
    assert summary["winner_index"] == 1
    assert summary["click_xy"] == [30, 30]
    assert "tiebreak_method" in summary
    assert (debug_dir / "winner.png").is_file()
    assert (debug_dir / "00_cutout.png").is_file()
    assert (debug_dir / "01_clip_crop.png").is_file()


def test_single_candidate_still_wins_when_gated_through() -> None:
    lone = _bgra(alpha_rect=(20, 20, 50, 60))
    result = select_best_cutout(
        [lone],
        click_xy=(35, 30),
        scorer=_scorer({0: _uniform_checks(0.80)}),
        selection_strategy=RelativeClipRankingStrategy(),
    )
    assert result.winner_index == 0
