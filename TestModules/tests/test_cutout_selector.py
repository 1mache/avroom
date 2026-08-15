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
    select_best_cutout,
)
from avroom_object_removal.core.cutout_selector import (  # noqa: E402
    _BAD_LABEL,
    _DEBUG_FOLDER,
    _GOOD_LABEL,
)

_H = 100
_W = 100


def _bgra(*, alpha_rect: tuple[int, int, int, int] | None) -> np.ndarray:
    """Build a BGRA cutout. ``alpha_rect`` is ``(x0, y0, x1, y1)`` exclusive."""
    image = np.zeros((_H, _W, 4), dtype=np.uint8)
    if alpha_rect is None:
        return image
    x0, y0, x1, y1 = alpha_rect
    image[y0:y1, x0:x1, :3] = (40, 80, 120)
    image[y0:y1, x0:x1, 3] = 255
    return image


def _scorer(probs_by_index: dict[int, float]) -> ClipZeroShotContentValidationStrategy:
    call_index = {"n": 0}

    def fake_score(_pil: Image.Image, labels: tuple[str, ...]) -> dict[str, float]:
        positive, negative = labels
        assert positive == _GOOD_LABEL
        assert negative == _BAD_LABEL
        index = call_index["n"]
        call_index["n"] += 1
        good_p = probs_by_index[index]
        return {positive: good_p, negative: 1.0 - good_p}

    return ClipZeroShotContentValidationStrategy(score_fn=fake_score)


def test_click_miss_is_prefiltered() -> None:
    cutout = _bgra(alpha_rect=(10, 10, 40, 40))
    result = select_best_cutout(
        [cutout],
        click_xy=(80, 80),
        scorer=_scorer({0: 0.99}),
    )
    assert result.winner_index is None
    assert result.scores == (0.0,)
    assert result.reasons == ("click_miss",)


def test_area_too_small_is_prefiltered() -> None:
    cutout = _bgra(alpha_rect=(20, 20, 21, 21))
    result = select_best_cutout(
        [cutout],
        click_xy=(20, 20),
        scorer=_scorer({0: 0.99}),
    )
    assert result.winner_index is None
    assert result.scores == (0.0,)


def test_area_too_large_is_prefiltered() -> None:
    cutout = _bgra(alpha_rect=(0, 0, 100, 100))
    result = select_best_cutout(
        [cutout],
        click_xy=(50, 50),
        scorer=_scorer({0: 0.99}),
    )
    assert result.winner_index is None
    assert result.scores == (0.0,)


def test_picks_highest_score_above_threshold() -> None:
    viable = (20, 20, 50, 50)
    cutouts = [_bgra(alpha_rect=viable), _bgra(alpha_rect=viable), _bgra(alpha_rect=viable)]
    result = select_best_cutout(
        cutouts,
        click_xy=(30, 30),
        scorer=_scorer({0: 0.41, 1: 0.82, 2: 0.70}),
    )
    assert result.winner_index == 1
    assert result.scores == (0.41, 0.82, 0.70)
    assert result.reasons == ("scored", "winner", "scored")


def test_debug_dump_writes_selection_json_and_winner() -> None:
    viable = (20, 20, 50, 50)
    cutouts = [_bgra(alpha_rect=viable), _bgra(alpha_rect=viable)]
    select_best_cutout(
        cutouts,
        click_xy=(30, 30),
        scorer=_scorer({0: 0.41, 1: 0.82}),
    )

    debug_dir = Path(__file__).resolve().parents[1] / Path(_DEBUG_FOLDER)
    summary = json.loads((debug_dir / "selection.json").read_text(encoding="utf-8"))
    assert summary["winner_index"] == 1
    assert summary["click_xy"] == [30, 30]
    assert (debug_dir / "winner.png").is_file()
    assert (debug_dir / "00_cutout.png").is_file()
    assert (debug_dir / "01_clip_crop.png").is_file()


def test_agreed_silhouette_beats_higher_clip_fragment() -> None:
    """A part of the object scores best on CLIP; two agreeing passes must win."""
    seat = _bgra(alpha_rect=(20, 20, 50, 42))
    chair_a = _bgra(alpha_rect=(18, 18, 52, 70))
    chair_b = _bgra(alpha_rect=(18, 18, 52, 70))
    result = select_best_cutout(
        [seat, chair_a, chair_b],
        click_xy=(35, 30),
        scorer=_scorer({0: 0.976, 1: 0.966, 2: 0.965}),
    )
    assert result.winner_index in (1, 2)
    assert result.reasons[0] == "scored"


def test_agreed_silhouette_beats_higher_clip_clutter() -> None:
    """Chair plus a neighbouring bag scores best on CLIP and still loses."""
    chair_a = _bgra(alpha_rect=(20, 20, 50, 60))
    chair_b = _bgra(alpha_rect=(20, 20, 50, 60))
    chair_and_bag = _bgra(alpha_rect=(12, 12, 70, 72))
    result = select_best_cutout(
        [chair_a, chair_b, chair_and_bag],
        click_xy=(35, 30),
        scorer=_scorer({0: 0.966, 1: 0.965, 2: 0.980}),
    )
    assert result.winner_index in (0, 1)


def test_largest_member_of_agreed_group_wins() -> None:
    """Near-identical masks differ by dropped pixels; keep the complete one."""
    clipped = _bgra(alpha_rect=(20, 20, 50, 56))
    full_a = _bgra(alpha_rect=(20, 20, 50, 60))
    full_b = _bgra(alpha_rect=(20, 20, 50, 60))
    result = select_best_cutout(
        [clipped, full_a, full_b],
        click_xy=(35, 30),
        scorer=_scorer({0: 0.976, 1: 0.966, 2: 0.965}),
    )
    assert result.winner_index in (1, 2)


def test_single_candidate_still_wins_when_gated_through() -> None:
    lone = _bgra(alpha_rect=(20, 20, 50, 60))
    result = select_best_cutout(
        [lone],
        click_xy=(35, 30),
        scorer=_scorer({0: 0.80}),
    )
    assert result.winner_index == 0


def test_all_below_threshold_returns_none() -> None:
    viable = (20, 20, 50, 50)
    cutouts = [_bgra(alpha_rect=viable), _bgra(alpha_rect=viable)]
    result = select_best_cutout(
        cutouts,
        click_xy=(30, 30),
        scorer=_scorer({0: 0.40, 1: 0.55}),
    )
    assert result.winner_index is None
    assert result.scores == (0.40, 0.55)
