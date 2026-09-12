from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock

import numpy as np

sys.modules.setdefault("torch", MagicMock())
sys.modules.setdefault("transformers", MagicMock())

from avroom_object_removal.ai_engines.mask_selection.mask_selection_tiebreak_strategy import (  # noqa: E402
    TiebreakRequest,
)
from avroom_object_removal.ai_engines.mask_selection.strategies.gemini_cutout_tiebreak_strategy import (  # noqa: E402
    GeminiCutoutTiebreakStrategy,
    _parse_pick_payload,
)

_SCENE = np.zeros((40, 40, 3), dtype=np.uint8)
_CROP = np.full((10, 10, 3), 128, dtype=np.uint8)


def _request(*, finalists: tuple[int, ...] = (0, 1)) -> TiebreakRequest:
    return TiebreakRequest(
        scene_bgr=_SCENE,
        click_xy=(20, 20),
        finalist_indices=finalists,
        cutout_crops_bgr={index: _CROP.copy() for index in finalists},
        clip_averages={0: 0.80, 1: 0.79},
    )


def test_parse_pick_payload_success() -> None:
    index, reason = _parse_pick_payload(
        '{"candidate_index": 1, "reason": "complete chair"}',
        (0, 1),
    )
    assert index == 1
    assert reason == "complete chair"


def test_parse_pick_payload_rejects_invalid_index() -> None:
    try:
        _parse_pick_payload('{"candidate_index": 9, "reason": "nope"}', (0, 1))
    except ValueError as exc:
        assert "not in allowed" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_parse_pick_payload_rejects_malformed_json() -> None:
    try:
        _parse_pick_payload("not json", (0, 1))
    except json.JSONDecodeError:
        pass
    else:
        raise AssertionError("expected JSONDecodeError")


def test_complete_fn_picks_winner() -> None:
    strategy = GeminiCutoutTiebreakStrategy(
        api_key="test-key",
        complete_fn=lambda _parts: '{"candidate_index": 0, "reason": "mock"}',
    )
    result = strategy.pick_among(_request())
    assert result.candidate_index == 0
    assert result.method == "gemini"
    assert result.reason == "mock"


def test_complete_fn_invalid_index_falls_back_to_clip() -> None:
    strategy = GeminiCutoutTiebreakStrategy(
        api_key="test-key",
        complete_fn=lambda _parts: '{"candidate_index": 99, "reason": "bad"}',
    )
    result = strategy.pick_among(_request())
    assert result.candidate_index == 0
    assert result.method == "clip_fallback"
    assert "clip_fallback" in result.reason


def test_placeholder_key_falls_back_without_network() -> None:
    strategy = GeminiCutoutTiebreakStrategy(api_key="your-api-key-here")
    result = strategy.pick_among(_request())
    assert result.candidate_index == 0
    assert result.method == "clip_fallback"
