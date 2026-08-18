from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from avroom_object_removal import (
    BackgroundInpainter,
    ImageInpaintingFacade,
    ImageInpaintingStrategy,
)


class _SolidColorInpaintStrategy(ImageInpaintingStrategy):
    """Stub strategy that returns a uniform BGR frame regardless of input."""

    def __init__(self, color: tuple[int, int, int]) -> None:
        self._color = np.array(color, dtype=np.uint8)

    def inpaint(self, image: np.ndarray, mask: np.ndarray, **kwargs: Any) -> np.ndarray:
        return np.full_like(image, self._color)


class _InpaintOutStubStrategy(ImageInpaintingStrategy):
    """Stub that records inpaint_out values for compose tests."""

    def __init__(self, color: tuple[int, int, int]) -> None:
        self._color = np.array(color, dtype=np.uint8)

    def inpaint(self, image: np.ndarray, mask: np.ndarray, **kwargs: Any) -> np.ndarray:
        inpaint_out = kwargs.get("inpaint_out")
        if isinstance(inpaint_out, dict):
            inpaint_out["compose_dilate_pixels"] = 2
            inpaint_out["verification_ok"] = True
        return np.full_like(image, self._color)


def test_cut_mask_from_image_preserves_pixels_outside_compose_mask() -> None:
    """Only compose-mask pixels should come from the inpainting model output."""
    original = np.zeros((4, 4, 3), dtype=np.uint8)
    original[:, :] = (10, 20, 30)

    inpaint_mask = np.zeros((4, 4), dtype=np.uint8)
    inpaint_mask[1:3, 1:3] = 255
    compose_mask = np.zeros((4, 4), dtype=np.uint8)
    compose_mask[2, 2] = 255

    model_color = (200, 100, 50)
    stub_facade = ImageInpaintingFacade(strategy=_SolidColorInpaintStrategy(model_color))
    inpainter = BackgroundInpainter(inpainting_facade=stub_facade)

    result = inpainter.cut_mask_from_image(
        original_image=original,
        mask=inpaint_mask,
        compose_mask=compose_mask,
    )

    compose_bool = compose_mask > 127
    inpaint_only_bool = (inpaint_mask > 127) & (~compose_bool)
    assert np.all(result[compose_bool] == np.array(model_color, dtype=np.uint8))
    assert np.array_equal(result[inpaint_only_bool], original[inpaint_only_bool])
    assert np.array_equal(result[~(inpaint_mask > 127)], original[~(inpaint_mask > 127)])


def test_cut_mask_from_image_empty_compose_mask_returns_original() -> None:
    """An empty compose mask should leave the original image unchanged."""
    original = np.full((3, 3, 3), (5, 15, 25), dtype=np.uint8)
    inpaint_mask = np.ones((3, 3), dtype=np.uint8) * 255
    compose_mask = np.zeros((3, 3), dtype=np.uint8)

    model_color = (99, 88, 77)
    stub_facade = ImageInpaintingFacade(strategy=_SolidColorInpaintStrategy(model_color))
    inpainter = BackgroundInpainter(inpainting_facade=stub_facade)

    result = inpainter.cut_mask_from_image(
        original_image=original,
        mask=inpaint_mask,
        compose_mask=compose_mask,
    )

    assert np.array_equal(result, original)


def test_compose_mask_padding_radius_expands_paste_region(monkeypatch: pytest.MonkeyPatch) -> None:
    """Padding should expand the compose region beyond the base compose mask."""
    original = np.zeros((5, 5, 3), dtype=np.uint8)
    original[:, :] = (10, 20, 30)

    inpaint_mask = np.ones((5, 5), dtype=np.uint8) * 255
    compose_mask = np.zeros((5, 5), dtype=np.uint8)
    compose_mask[2, 2] = 255

    model_color = (200, 100, 50)
    stub_facade = ImageInpaintingFacade(strategy=_SolidColorInpaintStrategy(model_color))
    inpainter = BackgroundInpainter(inpainting_facade=stub_facade)
    monkeypatch.setattr(BackgroundInpainter, "COMPOSE_MASK_PADDING_RADIUS", 1)

    result = inpainter.cut_mask_from_image(
        original_image=original,
        mask=inpaint_mask,
        compose_mask=compose_mask,
    )

    center_neighbors = [(1, 2), (2, 1), (2, 3), (3, 2)]
    for row, col in center_neighbors:
        assert np.array_equal(result[row, col], np.array(model_color, dtype=np.uint8))
    assert np.array_equal(result[0, 0], original[0, 0])


def test_inpaint_out_compose_dilate_expands_paste_region() -> None:
    """Verifier-driven compose dilation should widen the paste region."""
    original = np.zeros((5, 5, 3), dtype=np.uint8)
    original[:, :] = (10, 20, 30)

    inpaint_mask = np.ones((5, 5), dtype=np.uint8) * 255
    compose_mask = np.zeros((5, 5), dtype=np.uint8)
    compose_mask[2, 2] = 255

    model_color = (200, 100, 50)
    stub_facade = ImageInpaintingFacade(strategy=_InpaintOutStubStrategy(model_color))
    inpainter = BackgroundInpainter(inpainting_facade=stub_facade)

    result = inpainter.cut_mask_from_image(
        original_image=original,
        mask=inpaint_mask,
        compose_mask=compose_mask,
        inpaint_out={},
    )

    center_neighbors = [(1, 2), (2, 1), (2, 3), (3, 2)]
    for row, col in center_neighbors:
        assert np.array_equal(result[row, col], np.array(model_color, dtype=np.uint8))
    assert np.array_equal(result[0, 0], original[0, 0])
