from __future__ import annotations

import sys
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest
from PIL import Image

# Allow collection when optional GPU deps are absent in the test environment.
sys.modules.setdefault("torch", MagicMock())
sys.modules.setdefault("transformers", MagicMock())

from avroom_object_removal import (
    ClipZeroShotContentValidationStrategy,
    CompositeContentValidationStrategy,
    ContentImageValidator,
    ContentValidationFacade,
    ContentValidationResult,
    ContentValidationStrategy,
)


class _StubValidationStrategy(ContentValidationStrategy):
    """Returns a fixed result regardless of input."""

    def __init__(self, result: ContentValidationResult) -> None:
        self._result = result
        self.call_count = 0

    def validate(self, image: np.ndarray) -> ContentValidationResult:
        self.call_count += 1
        return self._result


def _encode_png_bgr(image_bgr: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".png", image_bgr)
    assert ok and buffer is not None
    return buffer.tobytes()


def test_content_image_validator_decodes_bytes_and_delegates() -> None:
    """Validator should decode bytes and forward BGR to the facade strategy."""
    stub_result = ContentValidationResult(
        is_valid=True,
        checks={"stub": True},
        scores={"stub_score": 1.0},
        messages=(),
    )
    stub = _StubValidationStrategy(stub_result)
    facade = ContentValidationFacade(strategy=stub)
    validator = ContentImageValidator(validation_facade=facade)

    image_bgr = np.full((8, 8, 3), (40, 80, 120), dtype=np.uint8)
    result = validator.validate_upload(
        image_path="memory://abc",
        image_bytes=_encode_png_bgr(image_bgr),
    )

    assert result.is_valid is True
    assert stub.call_count == 1


def test_content_image_validator_raises_on_invalid_bytes() -> None:
    """Invalid bytes should raise ValueError before strategy runs."""
    stub = _StubValidationStrategy(
        ContentValidationResult(is_valid=True, checks={}, scores={}, messages=())
    )
    validator = ContentImageValidator(validation_facade=ContentValidationFacade(strategy=stub))

    with pytest.raises(ValueError, match="not a valid image"):
        validator.validate_upload(image_path="memory://abc", image_bytes=b"not-an-image")


def test_composite_merges_checks_and_fails_when_any_child_fails() -> None:
    """Composite should union checks and fail if any child fails."""
    pass_strategy = _StubValidationStrategy(
        ContentValidationResult(
            is_valid=True,
            checks={"check_a": True},
            scores={"score_a": 0.9},
            messages=(),
        )
    )
    fail_strategy = _StubValidationStrategy(
        ContentValidationResult(
            is_valid=False,
            checks={"check_b": False},
            scores={"score_b": 0.1},
            messages=("child failed",),
        )
    )
    composite = CompositeContentValidationStrategy((pass_strategy, fail_strategy))
    image = np.zeros((4, 4, 3), dtype=np.uint8)

    result = composite.validate(image)

    assert result.is_valid is False
    assert result.checks == {"check_a": True, "check_b": False}
    assert result.scores == {"score_a": 0.9, "score_b": 0.1}
    assert result.messages == ("child failed",)


_SCENE_LABEL = "a photo of an indoor room or outdoor space"
_SCENE_ALTERNATIVE_LABEL = "a photo of something else"
_PERSON_LABEL = "a photo of a person, selfie, or portrait"
_PERSON_ALTERNATIVE_LABEL = "a photo of an empty room or outdoor space"
_PRODUCT_LABEL = "a product photo on plain background"
_PRODUCT_ALTERNATIVE_LABEL = "a photo of a room or outdoor space"
_SCREENSHOT_LABEL = "a screenshot or photo of a screen"
_SCREENSHOT_ALTERNATIVE_LABEL = "a photo of a real room or outdoor space"
_OBSTRUCTION_LABEL = "a photo with a hand or body blocking the camera"
_OBSTRUCTION_ALTERNATIVE_LABEL = "a clear photo of a room or outdoor space"
_NSFW_LABEL = "an explicit NSFW or nude photo"
_NSFW_ALTERNATIVE_LABEL = "a normal photo of a room or outdoor space"
_STYLIZED_LABEL = "an anime, painting, cartoon, or heavily filtered image"
_STYLIZED_ALTERNATIVE_LABEL = "a real photograph of a room or outdoor space"


def _binary_scores(positive: str, negative: str, positive_prob: float) -> dict[str, float]:
    """Return a 2-label distribution that sums to 1.0."""
    return {positive: positive_prob, negative: 1.0 - positive_prob}


def test_clip_strategy_scene_check_passes_with_high_positive_scores() -> None:
    """CLIP strategy should pass all checks when scene wins and bad concepts lose."""

    def fake_score(_pil_image: Image.Image, labels: tuple[str, ...]) -> dict[str, float]:
        positive, negative = labels
        if positive == _SCENE_LABEL:
            return _binary_scores(positive, negative, 0.9)
        if positive in {
            _PERSON_LABEL,
            _PRODUCT_LABEL,
            _SCREENSHOT_LABEL,
            _OBSTRUCTION_LABEL,
            _NSFW_LABEL,
            _STYLIZED_LABEL,
        }:
            return _binary_scores(positive, negative, 0.1)
        raise AssertionError(f"Unexpected binary pair: {labels}")

    strategy = ClipZeroShotContentValidationStrategy(
        score_fn=lambda pil, labels: fake_score(pil, labels),
    )
    image = np.full((16, 16, 3), 128, dtype=np.uint8)
    result = strategy.validate(image)

    assert result.is_valid is True
    assert result.checks["scene_space_or_landscape"] is True


def test_clip_strategy_fails_person_centric_when_person_score_high() -> None:
    """CLIP strategy should fail when person probability exceeds threshold."""

    def fake_score(_pil_image: Image.Image, labels: tuple[str, ...]) -> dict[str, float]:
        positive, negative = labels
        if positive == _PERSON_LABEL:
            return _binary_scores(positive, negative, 0.8)
        if positive == _SCENE_LABEL:
            return _binary_scores(positive, negative, 0.9)
        if positive in {
            _PRODUCT_LABEL,
            _SCREENSHOT_LABEL,
            _OBSTRUCTION_LABEL,
            _NSFW_LABEL,
            _STYLIZED_LABEL,
        }:
            return _binary_scores(positive, negative, 0.1)
        raise AssertionError(f"Unexpected binary pair: {labels}")

    strategy = ClipZeroShotContentValidationStrategy(
        score_fn=lambda pil, labels: fake_score(pil, labels),
    )
    image = np.full((16, 16, 3), 128, dtype=np.uint8)
    result = strategy.validate(image)

    assert result.is_valid is False
    assert result.checks["not_person_centric"] is False
    assert any("person" in msg.lower() for msg in result.messages)
