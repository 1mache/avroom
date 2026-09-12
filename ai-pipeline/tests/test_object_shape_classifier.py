"""Unit tests for planar vs volumetric CLIP classification."""

from __future__ import annotations

import numpy as np
from PIL import Image

from avroom_object_removal.core.object_shape_classifier import (
    PLANAR_LABELS,
    TIE_BAND,
    VOLUMETRIC_LABELS,
    classify_object_is_3d,
)


class _FakeScorer:
    """Returns a fixed softmax distribution keyed by label."""

    def __init__(self, scores: dict[str, float]) -> None:
        self._scores = scores

    def score_labels(self, pil_image: Image.Image, labels: tuple[str, ...]) -> dict[str, float]:
        assert isinstance(pil_image, Image.Image)
        return {label: self._scores[label] for label in labels}


def _solid_cutout(h: int = 32, w: int = 32) -> np.ndarray:
    bgra = np.zeros((h, w, 4), dtype=np.uint8)
    bgra[:, :, :3] = 180
    bgra[:, :, 3] = 255
    return bgra


def _score_map(*, volumetric: float, planar: float) -> dict[str, float]:
    """Build a full label->score map with uniform within-group values."""
    out: dict[str, float] = {}
    for label in VOLUMETRIC_LABELS:
        out[label] = volumetric
    for label in PLANAR_LABELS:
        out[label] = planar
    return out


def test_volumetric_wins_when_furniture_scores_higher() -> None:
    scorer = _FakeScorer(_score_map(volumetric=0.4, planar=0.1))
    assert classify_object_is_3d(_solid_cutout(), scorer=scorer) is True


def test_planar_wins_when_painting_scores_higher() -> None:
    scorer = _FakeScorer(_score_map(volumetric=0.1, planar=0.35))
    assert classify_object_is_3d(_solid_cutout(), scorer=scorer) is False


def test_tie_band_defaults_to_volumetric() -> None:
    # Means equal → within TIE_BAND → volumetric.
    scorer = _FakeScorer(_score_map(volumetric=0.25, planar=0.25))
    assert classify_object_is_3d(_solid_cutout(), scorer=scorer) is True

    # Difference exactly at the band edge still counts as a tie.
    half = TIE_BAND / 2
    scorer = _FakeScorer(_score_map(volumetric=0.25 + half, planar=0.25 - half))
    assert abs((0.25 + half) - (0.25 - half)) <= TIE_BAND
    assert classify_object_is_3d(_solid_cutout(), scorer=scorer) is True


def test_empty_cutout_defaults_to_volumetric() -> None:
    empty = np.zeros((16, 16, 4), dtype=np.uint8)
    scorer = _FakeScorer(_score_map(volumetric=0.0, planar=1.0))
    assert classify_object_is_3d(empty, scorer=scorer) is True
