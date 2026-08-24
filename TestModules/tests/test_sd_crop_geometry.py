"""Tests for the native-resolution crop logic in StableDiffusionInpaintingStrategy.

All tests run without torch by monkeypatching _load_stable_diffusion_pipe.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest

from avroom_object_removal.ai_engines.inpainting.inpaint_params import InpaintParams
from avroom_object_removal.ai_engines.inpainting.strategies.stable_diffusion_inpainting_strategy import (
    SD_MAX_GEN_SIDE,
    StableDiffusionInpaintingStrategy,
    _snap_to_multiple_of_8,
)


# ---------------------------------------------------------------------------
# _snap_to_multiple_of_8 unit tests
# ---------------------------------------------------------------------------


def test_snap_already_aligned() -> None:
    assert _snap_to_multiple_of_8(512, 512) == (512, 512)


def test_snap_rounds_up_to_8() -> None:
    w, h = _snap_to_multiple_of_8(527, 733)
    assert w % 8 == 0
    assert h % 8 == 0
    assert w >= 527
    assert h >= 733


def test_snap_minimum_is_8() -> None:
    w, h = _snap_to_multiple_of_8(1, 1)
    assert w == 8
    assert h == 8


def test_snap_respects_oom_cap() -> None:
    w, h = _snap_to_multiple_of_8(2000, 2000, max_side=1024)
    assert max(w, h) <= 1024
    assert w % 8 == 0
    assert h % 8 == 0


def test_snap_cap_does_not_trigger_at_typical_window() -> None:
    """A 528x734 window (the log case) must not hit the OOM cap."""
    w, h = _snap_to_multiple_of_8(528, 734)
    assert max(w, h) <= SD_MAX_GEN_SIDE
    # Should just round up by at most 7 px each side.
    assert w <= 528 + 7
    assert h <= 734 + 7


def test_snap_both_dims_divisible_by_8_after_cap() -> None:
    w, h = _snap_to_multiple_of_8(1600, 1200, max_side=SD_MAX_GEN_SIDE)
    assert w % 8 == 0
    assert h % 8 == 0
    assert max(w, h) <= SD_MAX_GEN_SIDE


# ---------------------------------------------------------------------------
# Round-trip integration: fake pipe, pixel-identity outside mask
# ---------------------------------------------------------------------------


def _make_fake_pipe(fill_color: tuple[int, int, int] = (200, 100, 50)) -> Any:
    """Return a mock pipe that always outputs a solid PIL image of the requested size."""
    from PIL import Image

    def fake_call(**kwargs: Any) -> Any:
        size = kwargs["image"].size  # (width, height)
        img = Image.new("RGB", size, fill_color)
        result = MagicMock()
        result.images = [img]
        return result

    pipe = MagicMock(side_effect=fake_call)
    return pipe


def _scene(h: int = 200, w: int = 300) -> tuple[np.ndarray, np.ndarray]:
    """Solid blue BGR image with a square mask in the center."""
    image = np.full((h, w, 3), (180, 40, 20), dtype=np.uint8)  # BGR blue-ish
    mask = np.zeros((h, w), dtype=np.uint8)
    cy, cx = h // 2, w // 2
    mask[cy - 20 : cy + 20, cx - 20 : cx + 20] = 255
    return image, mask


def test_output_shape_matches_input(monkeypatch: Any) -> None:
    image, mask = _scene()
    strategy = StableDiffusionInpaintingStrategy.__new__(StableDiffusionInpaintingStrategy)
    strategy._model_id = "fake"
    strategy._device = "cpu"
    strategy._prompt = "floor"
    strategy._negative_prompt = "shadow"

    monkeypatch.setattr(
        "avroom_object_removal.ai_engines.inpainting.strategies."
        "stable_diffusion_inpainting_strategy._load_stable_diffusion_pipe",
        lambda *_: _make_fake_pipe(),
    )

    out = strategy.inpaint(image, mask, InpaintParams(strength=0.35)).image
    assert out.shape == image.shape


def test_pixels_outside_mask_unchanged(monkeypatch: Any) -> None:
    """Every pixel NOT in the mask must be byte-identical to the original."""
    image, mask = _scene()
    strategy = StableDiffusionInpaintingStrategy.__new__(StableDiffusionInpaintingStrategy)
    strategy._model_id = "fake"
    strategy._device = "cpu"
    strategy._prompt = "floor"
    strategy._negative_prompt = "shadow"

    # Fake pipe returns a solid color that differs from the original background.
    monkeypatch.setattr(
        "avroom_object_removal.ai_engines.inpainting.strategies."
        "stable_diffusion_inpainting_strategy._load_stable_diffusion_pipe",
        lambda *_: _make_fake_pipe(fill_color=(100, 200, 50)),
    )

    out = strategy.inpaint(image, mask, InpaintParams(strength=0.35)).image
    mask_bool = mask > 127
    # Background region must be unchanged.
    np.testing.assert_array_equal(out[~mask_bool], image[~mask_bool])


def test_mask_region_receives_pipe_output(monkeypatch: Any) -> None:
    """Pixels inside the mask must come from the pipe, not from the original."""
    image, mask = _scene()
    fill = (100, 200, 50)  # RGB — will become BGR (50, 200, 100) in cv2

    strategy = StableDiffusionInpaintingStrategy.__new__(StableDiffusionInpaintingStrategy)
    strategy._model_id = "fake"
    strategy._device = "cpu"
    strategy._prompt = "floor"
    strategy._negative_prompt = "shadow"

    monkeypatch.setattr(
        "avroom_object_removal.ai_engines.inpainting.strategies."
        "stable_diffusion_inpainting_strategy._load_stable_diffusion_pipe",
        lambda *_: _make_fake_pipe(fill_color=fill),
    )

    out = strategy.inpaint(image, mask, InpaintParams(strength=0.35)).image
    mask_bool = mask > 127
    # Every masked pixel must NOT equal the original background.
    original_inside = image[mask_bool]
    out_inside = out[mask_bool]
    # At least some must differ (the pipe returned a different solid color).
    assert not np.array_equal(out_inside, original_inside)
