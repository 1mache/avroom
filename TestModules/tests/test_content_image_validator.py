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


def test_clip_strategy_scene_check_passes_with_high_positive_scores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLIP strategy should pass scene check when positive labels dominate."""

    def fake_score(_pil_image: Image.Image, labels: tuple[str, ...]) -> dict[str, float]:
        if "indoor room" in labels[0]:
            return {label: (0.8 if "room" in label or "landscape" in label else 0.05) for label in labels}
        if "single person" in labels[0]:
            return {label: 0.05 for label in labels}
        if "person" in labels[0]:
            return {label: 0.05 for label in labels}
        if "product" in labels[0]:
            return {label: 0.05 for label in labels}
        if "screenshot" in labels[0]:
            return {label: 0.05 for label in labels}
        if "hand" in labels[0]:
            return {label: 0.05 for label in labels}
        if "nude" in labels[0]:
            return {label: 0.05 for label in labels}
        if "anime" in labels[0]:
            return {label: 0.05 for label in labels}
        return {label: 0.05 for label in labels}

    strategy = ClipZeroShotContentValidationStrategy(
        score_fn=lambda pil, labels: fake_score(pil, labels),
    )
    image = np.full((16, 16, 3), 128, dtype=np.uint8)
    result = strategy.validate(image)

    assert result.is_valid is True
    assert result.checks["scene_space_or_landscape"] is True


def test_clip_strategy_fails_person_centric_when_person_score_high(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLIP strategy should fail when person label probability exceeds threshold."""

    def fake_score(_pil_image: Image.Image, labels: tuple[str, ...]) -> dict[str, float]:
        if "indoor room" in labels[0]:
            return {label: 0.5 for label in labels}
        if "single person" in labels[0]:
            return {label: 0.05 for label in labels}
        if "person" in labels[0]:
            return {label: 0.9 for label in labels}
        return {label: 0.05 for label in labels}

    strategy = ClipZeroShotContentValidationStrategy(
        score_fn=lambda pil, labels: fake_score(pil, labels),
    )
    image = np.full((16, 16, 3), 128, dtype=np.uint8)
    result = strategy.validate(image)

    assert result.is_valid is False
    assert result.checks["not_person_centric"] is False
    assert any("person" in msg.lower() for msg in result.messages)
